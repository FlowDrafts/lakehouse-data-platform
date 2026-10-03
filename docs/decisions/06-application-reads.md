# ADR-06: Application read paths: money from the owning service, derived data from Aurora

| | |
|---|---|
| **Status** | Accepted (depends on an app-traffic assumption that hasn't been measured) |
| **Date** | 2026-10-03 |
| **Decision-makers** | Gaurav |
| **Related** | [Design doc](../architecture/lakehouse-design.md) §5, §7.4, §10.3 · [ADR-08](08-the-fast-path.md) |

## Context and Problem Statement

Apps show two kinds of number:
- **Money:** a balance, an amount owed, a settlement status.
- **Derived data:** transaction history across products, monthly summaries, eligibility flags, and
  masked display values.

The lake runs behind on purpose. Gold publishes about every 15 minutes, only after it reconciles,
and it can be held for hours if a check fails. Where should each kind of number come from, and
what store should serve the derived data?

## Decision Drivers

- The money a customer sees must always be current.
- No screen may mix data from two versions.
- Point lookups must be fast enough for apps, at app scale.
- Analytics load must stay off the systems that process money.

## Considered Options

**Where money comes from**

| Option | Pros | Cons |
|---|---|---|
| From the lake, through the serving store | One read path | Up to about 20 minutes stale, and frozen while a table is held. A customer who paid at 10:02 still sees the old amount at 10:05 |
| **Live from the owning service** (its API or a read replica) | Always current; the source stays the system of record | Two read paths in every app |

**Where derived data is served from**

| Option | Pros | Cons |
|---|---|---|
| **Aurora PostgreSQL**, in a separate serving cluster | A version swaps in with one transaction (load a staging table, then rename); SQL for summaries; the team already runs Postgres | Read capacity has a ceiling; large refreshes are heavy writes |
| DynamoDB | Single-digit milliseconds at any scale; serverless; handles spiky traffic | Can't swap in a whole version at once: needs a table per version, or a version stamp on every row that the Read API filters on |
| A ClickHouse replica for apps | No new technology | Built for analytical scans, not high-concurrency point lookups; sharing it with BI ties app latency to dashboards |
| Cassandra / Amazon Keyspaces | Scales like DynamoDB | Adds nothing over DynamoDB for this access pattern |
| Redis / MemoryDB | Under a millisecond | Too costly in memory to hold history; a cache, not a store |
| Pushing results back into the services | One read path | Analytics output lands in money-processing databases, with no clear owner |

## Decision Outcome

Chosen option: **money live from the owning service, and derived data from Aurora PostgreSQL
behind the Read API**. Money must always be current, and the derived store must swap in whole
versions atomically.

**Money** is read live through the owning service's API or a read replica. It never comes from the
lake, and apps never read another team's primary database. The sources stay the system of record.

**Derived data** comes from Aurora PostgreSQL, in its own cluster:
- **Loading.** Each published version is loaded into a staging table, then swapped in with one
  transaction. The rename takes a brief exclusive lock, so the swap runs with `lock_timeout` and
  retries.
- **Access.** The Read API is the only way in, and every response carries the version label.
- **Refresh.** Each kind of data refreshes as often as it changes, and is always swapped in whole.
  Recent history refreshes with every gold publish; summaries and eligibility refresh daily.
- **Upgrade path.** If peak reads outgrow Aurora's replicas, or traffic turns spiky, move to
  DynamoDB. Each version then gets its own table, and the Read API switches tables in one step.
- **Caching.** Redis may sit in front as a cache, never as the store.

**Assumption:** peak reads are in the low thousands per second, and refreshes happen no more often
than each gold publish. Neither has been measured.

### Consequences

- Every app has two read paths, and every screen must be classified as money or derived. That's a
  product decision for each screen, and getting it wrong is the real risk.
- Another Postgres cluster to run. This data is derived and spans products, so no single service
  can compute it without putting analytics load on a money-processing system.
- The serving copy can lag gold. The version label makes the lag visible.
- Fast-path signals are a third kind of answer, always labelled unverified
  ([ADR-08](08-the-fast-path.md)).

### Confirmation

Tests S.1, S.2 and S.6 in the [test plan](../../tests/README.md).

## More Information

Revisit if measured traffic exceeds the assumption. Derived reads then move to DynamoDB, with one
table per version.
