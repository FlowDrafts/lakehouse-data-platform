# ADR-01: AWS Glue as the catalog, with consistency enforced at read time

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-03 |
| **Decision-makers** | Gaurav |
| **Related** | [Design doc](../architecture/lakehouse-design.md) §6.3, §7.3, §10.3 · [ADR-05](05-the-publish-gate.md) |

## Context and Problem Statement

Every Iceberg table needs a catalog to record its current snapshot. Gold tables are built from
several silver tables, and readers join gold tables together, so tables must agree on *as of
when*. Glue commits one table at a time, and so do Spark's writers. A publish that flips several
tables atomically isn't available to our jobs without custom code, whatever the catalog supports.
How do readers get a consistent view?

## Decision Drivers

- A reader must never see a mix of versions without being able to tell.
- Positions from different sources (each database's change log, each partner file's version) can't
  be compared with one another.
- Operating cost on an AWS-native stack.
- Maturity at this scale.

## Considered Options

| Option | Pros | Cons |
|---|---|---|
| **AWS Glue** | Managed, with no servers to run; native to IAM and Lake Formation; exposes an Iceberg REST endpoint | Commits one table at a time |
| Nessie | Catalog-wide branches and multi-table commits | A second stateful service that every commit depends on; a thinner production record at this scale |
| Apache Polaris | Open; strong cross-engine access control | Incubating at the ASF; its main strength, cross-engine access control, isn't a requirement here |
| Amazon S3 Tables | AWS-managed Iceberg with compaction built in | The newest of the four; ties table layout and maintenance to the service |

## Decision Outcome

Chosen option: **AWS Glue**, because it's managed and AWS-native, and the consistency Nessie would
give at write time can be enforced at read time instead.

- Every publish stamps a **version label** on the commit, as an Iceberg snapshot property. It
  records the input positions the table was built from, **one per source**, never collapsed into
  a single number.
- Readers resolve **the latest published version**, never the raw latest snapshot. This applies to
  Spark, the ClickHouse load, the Aurora load and Cube.
- Every copy outside the lake carries the version it was loaded from, and every answer served from
  the lake returns it.

### Consequences

- Readers can't read "latest"; they must resolve a published version.
- Two gold tables published separately can be at different versions. The Read API pins both; a
  raw SQL user may not.
- Version bookkeeping is ours to build and keep correct.

### Confirmation

Tests 2.3 (the label rides on the commit), 2.10 (readers see version N or N+1, never part of
each), S.2 (the Read API pins versions) and S.4 (a lagging copy shows its gap) in the [test plan](../../tests/README.md).

## More Information

Revisit when two tables must flip together, for example a ledger and its summary that must never
be seen out of step. Nessie then earns its operating cost.
