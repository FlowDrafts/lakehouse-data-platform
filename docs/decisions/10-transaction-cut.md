# ADR-10: Advance silver to a consistent transaction cut, not to whatever has landed

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-03 |
| **Decision-makers** | Gaurav |
| **Related** | [Design doc](../architecture/lakehouse-design.md) §10.3 · [ADR-03](03-database-changes-into-the-lake.md) · [ADR-05](05-the-publish-gate.md) · [Runbook](../runbooks/cdc-slot-and-resnapshot.md) |

## Context and Problem Statement

One Postgres transaction, such as a loan and its two ledger lines, reaches the lake as events on
different topics and partitions, which land at different moments:
- Merged as they land, silver briefly holds the loan without its ledger lines. Gold built then
  ties to silver, because silver itself is torn, and shows a disbursed loan with no money moved.
- "Has the day been read past its cut-off?" can't be answered per partition either. An idle
  partition and a lagging one look the same, and lending alone has about 36.

How does silver reach a point that is both consistent across tables and provably complete?

## Decision Drivers

- Gold must never read a transaction half-applied across tables.
- The gate needs a completeness signal for each database source.
- It must use standard Debezium features, not custom capture code.
- It must survive at-least-once delivery and partitions that fall behind.

## Considered Options

| Option | Pros | Cons |
|---|---|---|
| Merge each table as its events land | Freshest silver; simplest | Torn reads; no way to know a day is complete |
| Advance to the highest position seen, holding back the last transaction in each batch | Cheap | Wrong across partitions: an earlier transaction can still be missing events in a partition that's behind |
| Outbox events only | Each event is a complete fact | Needs every service to write an outbox; doesn't cover current-state tables |
| **Debezium transaction metadata, and the longest complete prefix** | Exact: every transaction's event count per table is known | One more topic and table; silver waits for the slowest partition |

## Decision Outcome

Chosen option: **Debezium transaction metadata, advancing to the longest complete prefix**,
because it is the only option that is exact across tables and partitions.

1. Debezium writes BEGIN and END records (`provide.transaction.metadata`) to a topic with **one
   partition**, so its order is commit order. Each END states the event count for every table.
2. A transaction has landed when bronze holds exactly that many distinct events for each table.
3. **The cut is the longest prefix of landed transactions.** A complete transaction behind an
   incomplete one waits.
4. Every table of the source merges only the changes inside the cut, and each is tagged
   `cut_<source>_<position>`. Gold reads all its inputs at the same tag.
5. A business date is complete once the cut holds a transaction committed after the date's
   cut-off. Heartbeats write a small transaction regularly, so an idle source still passes.

### Consequences

- Silver is as fresh as the slowest partition of the source, not the fastest.
- One failed merge holds every table of that source at the previous cut.
- Exported and snapshot rows carry no transaction id. They are loaded before streaming begins,
  as the base of each incarnation.
- Tags are kept for 7 days. Gold must build from a cut younger than that.
- Debezium's END timing and event counts are assumed from its documentation, not yet verified
  against a running Debezium.

### Confirmation

Tests 3.1–3.5 in the [test plan](../../tests/README.md), and the `cut-*` entries in mutation
testing.

## More Information

Revisit if a source needs fresher silver than its slowest partition allows. That source then
moves to outbox events for the facts that need it.
