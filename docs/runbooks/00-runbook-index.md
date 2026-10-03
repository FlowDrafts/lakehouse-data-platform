# Runbooks

Procedures for the on-call engineer. Each runbook covers one area. It names what can go wrong, how
to tell the failures apart, and how each is resolved. The reasoning behind each design is in the
linked decision records.

**Scope.** These runbooks set out the failures and the recovery path for each. Exact commands,
dashboard links, access requests and per-environment settings depend on the deployed platform. They
are out of scope for this design, and get filled in when the platform is built.

## Runbooks

| Runbook | Covers | Decision records |
|---|---|---|
| [Partner and ops files](partner-files.md) | Missing, rejected, truncated or out-of-order files; reference updates | [ADR-04](../decisions/04-partner-and-ops-files.md) |
| [CDC replication slot and re-snapshot](cdc-slot-and-resnapshot.md) | A stalled connector, slot lag, an invalidated slot, a database restore or failover, the re-snapshot procedure | [ADR-02](../decisions/02-personal-data-tokenisation.md), [ADR-03](../decisions/03-database-changes-into-the-lake.md), [ADR-09](../decisions/09-one-time-migration.md) |
| [Publish gate hold](publish-gate-held.md) | Completeness holds, reconciliation breaks, a refused publish, corrections to closed dates | [ADR-01](../decisions/01-catalog-and-consistency.md), [ADR-05](../decisions/05-the-publish-gate.md) |

## Alert Routing

**Page:** someone acts now. **Ticket:** handled the next business day.

| Alert | Severity | Runbook |
|---|---|---|
| Replication-slot lag above threshold | Page | [CDC](cdc-slot-and-resnapshot.md) |
| Replication slot invalidated | Page | [CDC](cdc-slot-and-resnapshot.md) |
| Connector task failed | Page | [CDC](cdc-slot-and-resnapshot.md) |
| Silver behind bronze beyond its freshness target | Ticket | [CDC](cdc-slot-and-resnapshot.md) |
| Transaction cut not advancing | Page | [CDC](cdc-slot-and-resnapshot.md) |
| Gate check failed (any break) | Page | [Publish gate](publish-gate-held.md) |
| Gate hold open for more than 24 hours | Page | [Publish gate](publish-gate-held.md) |
| Gold older than its freshness target | Ticket | [Publish gate](publish-gate-held.md) |
| Publish refused because main moved | Ticket | [Publish gate](publish-gate-held.md) |
| File missing when its arrival window closes | Page for money feeds and watchlists; otherwise ticket | [Partner files](partner-files.md) |
| Truncation guard hold | Page for money feeds and watchlists; otherwise ticket | [Partner files](partner-files.md) |
| File rejected | Ticket | [Partner files](partner-files.md) |
| Change-only feed stopped at a gap | Ticket | [Partner files](partner-files.md) |

## Not Covered

| Situation | Where it's handled |
|---|---|
| Fast path (Flink) down, or drifting from gold | Each use case declares its own default: allow without a score, or hold ([ADR-08](../decisions/08-the-fast-path.md)) |
| Region lost | Recovery in `ap-south-2` is designed, not built. A runbook would imply a readiness that doesn't exist |
| Erasure request | Not yet written. The rule, by retention class, is set in [ADR-02](../decisions/02-personal-data-tokenisation.md) |
| Compaction, small files, commit retries | Routine maintenance scheduled by Airflow ([design doc](../architecture/lakehouse-design.md) §9.1) |
