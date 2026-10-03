# ADR-09: One-time migration: a bulk export joined to the change stream at the slot's starting position

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-03 |
| **Decision-makers** | Gaurav |
| **Related** | [Design doc](../architecture/lakehouse-design.md) §7.2 · [ADR-02](02-personal-data-tokenisation.md) · [ADR-03](03-database-changes-into-the-lake.md) · [ADR-04](04-partner-and-ops-files.md) |

## Context and Problem Statement

Years of data already sit in the service databases and in partner file archives. The change stream
only captures changes from the moment it starts. How do we load the existing data once, with no
gap, no lost change and no strain on production?

## Decision Drivers

- No change may be lost between the bulk load and the stream.
- No load on the production primary.
- Years of history should not flow through Kafka.
- The handover must be provable by test.

## Considered Options

| Option | Pros | Cons |
|---|---|---|
| Debezium's built-in initial snapshot | No extra tooling | Holds the replication slot open for hours on large tables, while Postgres keeps WAL the whole time |
| Debezium's incremental snapshot | Runs online; no separate export | Pushes years of rows through Kafka and the connector: slow, and it strains Kafka retention |
| **Create the slot, export from a replica, load directly, then stream from the slot** | History bypasses Kafka and the primary; the merge absorbs any overlap | An export pipeline to build and run once |

## Decision Outcome

Chosen option: **create the slot, export from a replica, load directly into bronze, then stream
from the slot**, because history bypasses Kafka and the primary, and correctness doesn't depend on
timing the export exactly.

**Database history**
1. **Create the replication slot first**, and record its starting position.
2. **Export the database afterwards, from a replica.** This uses RDS snapshot export to S3, as
   Parquet. The export can't be taken at exactly the slot's position, and it doesn't need to be.
3. **Load the export into bronze**, tagging every row with the slot's starting position:
   - **never zero**, because a row tagged zero loses every conflict and can never be corrected;
   - **never later than the export's true state**, because changes in between would then be
     ignored as stale.
4. **Stream from the slot.** Changes captured in both the export and the stream are re-applied in
   order by the strictly-newer merge ([ADR-03](03-database-changes-into-the-lake.md)), so the
   final state is correct.

**Partner archives**
- Archived partner files replay through the File Loader, oldest first
  ([ADR-04](04-partner-and-ops-files.md)).
- Files without sequence numbers or trailers load under a legacy contract. They are ordered by
  business date and labelled as more weakly checked.

**Tokenisation and gold**
- History is tokenised through a separate, rate-limited batch path to the vault
  ([ADR-02](02-personal-data-tokenisation.md)).
- Gold for past dates is rebuilt from silver and checked against the old finance reports where
  they exist. Every difference is explained and signed off.

**Moving consumers**
- Old and new run side by side, and each metric is reconciled and signed off by its owner.
- Consumers cut over one at a time, dashboards first and applications last.
- The old system stays read-only until it is retired.

### Consequences

- **A history gap.** Current-state tables hold only today's value. So "as known at" before
  migration day exists only where the source kept history tables.
- During catch-up, silver can briefly show an older state for rows that changed after the slot
  was created. Gold isn't published until the stream has been read past the export, so readers
  never see it.
- A one-time load on the vault, and the cost of running old and new in parallel during cutover.
- Legacy files carry weaker guarantees, and are labelled as such.

### Confirmation

Tests M.1–M.3 in the [test plan](../../tests/README.md).

## More Information

This runs once, at go-live. A database restore later reuses the same procedure, with a new
incarnation number ([ADR-03](03-database-changes-into-the-lake.md),
[runbook](../runbooks/cdc-slot-and-resnapshot.md)).
