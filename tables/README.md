# Table Definitions

The DDL for the platform's tables, one folder per engine. Files are numbered in the order they
are applied. These are samples, one table for each layer or kind, to show the shape and the layout
choices.

**Scope.** A full set of tables, and the migration tooling that applies them, are out of scope
for this design.

## Why It's Needed

Some of the design's guarantees live in a table's definition, not in code:
- **Partitioning and bucketing** decide merge cost and commit contention. Silver is bucketed on
  its merge key, and partner rows are partitioned per delivery.
- **Merge-on-read** keeps silver's continuous merges cheap.
- **Integer paise** everywhere: no float or decimal column holds money.
- **The control tables** (file register, current-version pointer, source totals) are part of how
  files are loaded and how the gate reconciles.

The contracts describe what a dataset means. The DDL describes how it is stored. The tests
create the same shapes on a local catalog (see [tests](../tests/README.md)).

## Contents

| File | Holds | Decision |
|---|---|---|
| [iceberg/01_bronze.sql](iceberg/01_bronze.sql) | Database changes as received, and Debezium's transaction records | [ADR-03](../docs/decisions/03-database-changes-into-the-lake.md), [ADR-10](../docs/decisions/10-transaction-cut.md) |
| [iceberg/02_silver.sql](iceberg/02_silver.sql) | A current-state table, and every version of a partner delivery's rows | [ADR-03](../docs/decisions/03-database-changes-into-the-lake.md), [ADR-04](../docs/decisions/04-partner-and-ops-files.md) |
| [iceberg/03_gold.sql](iceberg/03_gold.sql) | A gold table | [ADR-05](../docs/decisions/05-the-publish-gate.md) |
| [iceberg/04_control.sql](iceberg/04_control.sql) | File register, current-version pointer, source control totals | [ADR-04](../docs/decisions/04-partner-and-ops-files.md), [ADR-05](../docs/decisions/05-the-publish-gate.md) |
| [clickhouse/01_bi_copy.sql](clickhouse/01_bi_copy.sql) | The BI copy of gold, and which version it holds | [ADR-07](../docs/decisions/07-bi-serving.md) |
| [aurora/01_read_api.sql](aurora/01_read_api.sql) | Derived data behind the Read API | [ADR-06](../docs/decisions/06-application-reads.md) |

## Conventions

- **Names** are `<catalog>.<layer>.<table>`, for example `glue.silver.loan`.
- **Money** is a signed integer number of paise; rates are integer basis points.
- **Timestamps** are stored in UTC. The business date is assigned at the source, in Asia/Kolkata.
- **Personal data** appears only as vault tokens.

## Changing a Table

- An applied file is never edited. A change is a new numbered file, usually an `ALTER TABLE`.
- CI applies the files in order, with the job image for Iceberg and ClickHouse, and Flyway for Aurora. Every
  statement is idempotent (`IF NOT EXISTS`).
- Changing a partition spec affects only new data, so plan it with compaction.
