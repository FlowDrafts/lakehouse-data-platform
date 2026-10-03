# ADR-07: BI on a ClickHouse copy of published gold, with Cube defining each metric once

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-03 |
| **Decision-makers** | Gaurav |
| **Related** | [Design doc](../architecture/lakehouse-design.md) §6.3, §7.4 · [ADR-01](01-catalog-and-consistency.md) · [ADR-05](05-the-publish-gate.md) |

## Context and Problem Statement

Analysts and finance need dashboards that respond in under a second, and a chat interface (an MCP
bot). Both must give the same number for the same question. Auditors also need to see exactly what
a number was at month-end. What should BI read from?

## Decision Drivers

- Sub-second dashboards at this scale.
- One definition per metric, shared by dashboards and the chat bot.
- Never show a version that failed the gate.
- Month-end figures reproducible for audit.

## Considered Options

| Option | Pros | Cons |
|---|---|---|
| Cube on Trino or Spark, reading Iceberg directly | No copy; history and time travel built in | Seconds on a cache miss; one more engine to run for concurrency |
| Cube's own cache over Iceberg | No separate database | Every dashboard depends on what's cached, and a miss falls back to a slow scan |
| **ClickHouse copy of published gold, with Cube on top** | Sub-second at this scale; one metric definition for dashboards and chat | A second copy, with no history |

## Decision Outcome

Chosen option: **a ClickHouse copy of published gold, with Cube on top**, because it's the only
option that gives sub-second dashboards with one shared metric definition.

- **Loading.** Only a published gold version is loaded into ClickHouse. It goes into a staging
  table, then `EXCHANGE TABLES` swaps it in atomically, so dashboards never see a partial load.
  Each load carries its version label.
- **One definition per metric.** Cube defines each metric once. Its `refresh_key` is bound to the
  published version, so pre-aggregations are only ever rebuilt from versions that passed the gate.
- **Querying.** Dashboards and the MCP bot both query through Cube. Direct ClickHouse access is
  for exploration only, and is labelled that way.
- **Audits** read Iceberg through Spark, using time travel and month-end tags. That's the same
  engine that wrote the tables.

### Consequences

- A second copy, which must always match the version it came from.
- The copy keeps no history. "What did the dashboard show at 1:20?" is answered from Iceberg.
- Two read engines: ClickHouse for BI; Spark for audit, ad hoc queries and data science.
- Querying ClickHouse directly bypasses the metric definitions. That's handled by policy and
  labelling, not enforcement.
- Cube's `refresh_key` binding must be verified on the version actually deployed.

### Confirmation

Tests S.4 and S.5 in the [test plan](../../tests/README.md).

## More Information

Revisit if dashboards turn out to be fast enough reading Iceberg directly; then drop the copy.
