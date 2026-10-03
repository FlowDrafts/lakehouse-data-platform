# ADR-03: Database changes: the connector appends to bronze, and Spark merges into silver in order

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-03 |
| **Decision-makers** | Gaurav |
| **Related** | [Design doc](../architecture/lakehouse-design.md) §7.1, §9.3 · [ADR-09](09-one-time-migration.md) · [ADR-10](10-transaction-cut.md) · [Runbook](../runbooks/cdc-slot-and-resnapshot.md) |

## Context and Problem Statement

Lending, insurance and recharge each run on Postgres. Silver's current-state tables must equal the
source however changes arrive: replayed, reordered, deleted, or deleted before they were ever
inserted. How should changes get from the change log into silver?

## Decision Drivers

- The same final state under replay, reordering and deletes.
- Bronze must be an independent, append-only replay copy.
- The ordering guarantees must live in code we can test.
- 10k events/s at peak.

## Considered Options

| Option | Pros | Cons |
|---|---|---|
| Spark streaming merges straight into silver | One engine | One job writes bronze and silver, so bronze stops being an independent replay copy |
| Iceberg Sink Connector upserts into silver | No merge code to own | No ordering guard. A replayed older change overwrites a newer one. A delete that arrives before its insert is dropped, so the insert later resurrects the row. A truncate has no defined handling. And silver gets a second writer |
| **Iceberg Sink Connector appends to bronze; Spark merges into silver in order** | Appending can't corrupt anything; the ordering guarantees live in tested code | Two hops, and merge code to own |
| AWS DMS | Managed | Another opaque correctness layer between us and the change log |

## Decision Outcome

Chosen option: **the connector appends to bronze, and Spark merges into silver in order**, because
it's the only option where bronze stays an independent replay copy and the ordering guarantees are
code we test.

Spark merges the changes inside the transaction cut ([ADR-10](10-transaction-cut.md)) into
silver, with these guards:
1. **Strictly newer only.** A change applies only if it is newer: a higher incarnation, or the
   same incarnation and a greater change-log position. Replays and late arrivals become no-ops.
2. **A delete clears the row's business values**, so the final state doesn't depend on arrival
   order.
3. **A delete for a key never seen is stored as a tombstone**, so a late insert can't bring the row
   back.
4. **A table truncate fails the batch loudly**, instead of writing nulls over real values.
5. **An unchanged large column keeps its value.** Postgres omits unchanged large (TOAST) values
   from an update, and Debezium sends a placeholder that must never overwrite the real value.

**Kafka and Debezium settings this depends on**

- Topics are partitioned on the source primary key, so each key's changes stay in order.
- Retention is 7 days, and topics are **never log-compacted**: compaction would throw away the
  versions that replay depends on.
- 3 replicas, `min.insync.replicas=2`, and producers on `acks=all` with idempotence.
- Debezium heartbeats keep idle databases advancing their slot: `heartbeat.interval.ms`, plus
  `heartbeat.action.query` writing to a heartbeat table where the database itself is idle. This
  stops WAL accumulating, and lets completeness pass the day's cut-off
  ([ADR-05](05-the-publish-gate.md)).

### Consequences

- Two hops: bronze within about 2 minutes, silver within about 7.
- The merge is ours to own, test and tune. Its throughput at 10k events/s is unmeasured.
- **A database restore resets change-log positions**, so new changes look older than ones already
  applied. A failover can lose the replication slot. Either way, the
  [runbook](../runbooks/cdc-slot-and-resnapshot.md) forces a re-snapshot with a new incarnation
  number, then sweeps away rows the snapshot didn't see. This is designed, not built.

### Confirmation

Each guard has a test that fails when the guard is removed (mutation testing): tests C.1–C.6 and
M.1–M.2 in the [test plan](../../tests/README.md).

## More Information

Revisit when the merge can't keep up. The answer is to move the merge to Flink with the same
guards, not to switch to connector upserts.
