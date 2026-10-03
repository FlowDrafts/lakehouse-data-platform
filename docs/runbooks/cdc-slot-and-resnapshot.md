# Runbook: CDC Replication Slot and Re-snapshot

| | |
|---|---|
| **Owner** | Data platform on-call |
| **Severity** | Page: slot lag above threshold, slot invalidated, connector task failed. Ticket: silver behind bronze |
| **Last reviewed** | 2026-10-03 |
| **Related** | [ADR-03](../decisions/03-database-changes-into-the-lake.md) · [ADR-10](../decisions/10-transaction-cut.md) · [ADR-02](../decisions/02-personal-data-tokenisation.md) · [ADR-09](../decisions/09-one-time-migration.md) · [Design doc](../architecture/lakehouse-design.md) §7.1, §9.3 |

**Scope.** This runbook names each failure, how to recognise it and how it is resolved. Exact
commands and environment settings are out of scope for this design ([index](00-runbook-index.md)).

## Overview

Each Postgres database streams its changes through a logical replication slot. The path is
Debezium, then Kafka, then the connector appending to bronze, then Spark merging into silver. The
slot makes Postgres keep WAL until Debezium confirms it. Two things are at stake.

- **The source's disk.** WAL piles up while the connector is stalled. `max_slot_wal_keep_size`
  caps it. Past the cap, Postgres invalidates the slot rather than fill the disk.
- **Silver's completeness.** Changes can be lost for good: when the slot is invalidated, or when
  Kafka expires changes the lake never read. Those changes can't be replayed, so the only
  recovery is a re-snapshot.

Gold is never at risk directly. A source that is behind holds the gold tables that depend on it at
the gate, and their last good version keeps serving.

## Rules

1. **Never let clear text through to keep the stream moving.** `errors.tolerance` stays `none`. A
   vault outage stops the connector, by design.
2. **Never reset a slot or the connector's offsets without a re-snapshot.** Skipping ahead loses
   the changes in between, silently.
3. **Never compact change topics or shorten their retention** to free space.
4. **Raising `max_slot_wal_keep_size` is the source DBA's call.** It spends the primary's disk to
   avoid a re-snapshot.

## Triage and Resolution

| Symptom | Check | Likely cause | Resolution |
|---|---|---|---|
| Slot lag rising; connector task `FAILED` | The task's error | Vault unreachable (fail closed); a column the contract doesn't classify; a blocked change to a money column's type; Kafka unavailable | Fix the cause, then restart the task. It resumes from the slot's confirmed position, and the merge ignores anything replayed |
| Slot lag rising; connector `RUNNING` | Producer errors; Connect worker resources | Kafka throttling, or a starved worker | Fix capacity. The connector catches up from the slot |
| Slot lag rising on a database with little traffic | Whether heartbeat events are arriving | Heartbeats missing. A database that is itself idle needs `heartbeat.action.query` writing to a heartbeat table, not only `heartbeat.interval.ms` | Enable heartbeats. This also releases completeness holds waiting on that source's cut-off |
| `safe_wal_size` approaching zero | `pg_replication_slots` | The stall will outlast the WAL budget | Escalate to the source DBA now. Either raise the cap temporarily, or accept losing the slot and plan a re-snapshot |
| Slot invalidated (`wal_status = lost`) | `pg_replication_slots` | The stall outlasted `max_slot_wal_keep_size` | **Re-snapshot** |
| Bronze sink down for more than 7 days | The sink's committed offsets against each topic's earliest offset | Kafka expired changes the lake never read | **Re-snapshot** |
| Database restored from a backup | The owning team's restore notice | Change-log positions reset, so new changes look older than ones already applied and would be ignored | **Re-snapshot** |
| Failover to a standby | Whether the slot exists on the new primary | Logical slots aren't carried over unless failover slots are configured (Postgres 17+) | Slot missing: **re-snapshot**. Slot present: restart the connector |
| The merge fails on a truncate | The Spark job error for that table | The source table was truncated | Confirm with the owning team, then re-snapshot that table only (below) |
| Silver stops advancing; the transaction cut is stuck | The first incomplete transaction: its END record's count per table against the events in bronze | One partition is behind, or an event was lost (Kafka retention passed, a sink failure) | Behind: wait, or fix the sink. Lost: **re-snapshot**. Never skip the transaction: everything after it would be torn ([ADR-10](../decisions/10-transaction-cut.md)) |
| Silver behind bronze while bronze is current | Merge duration; delete-file counts | Merge throughput or small files at peak | Compact closed partitions, and scale the merge job. If it persists, see design-doc risk 1 |

## Re-snapshot

A re-snapshot reloads current state from the source. It reuses the one-time migration procedure
([ADR-09](../decisions/09-one-time-migration.md)).

1. **Hold the affected gold tables** by marking the source incomplete. Their previous version keeps
   serving, labelled with its age.
2. **Increment the source's incarnation number.** Changes are ordered by incarnation first, then by
   change-log position. So everything from the new incarnation outranks what is already in silver,
   even when its position is lower.
3. **Create a new slot** and record its starting position.
   - Start the connector with fresh offsets, under a new connector name or after an offset reset.
     Offsets stored from the old slot would be misread.
   - Set the connector to stream only, with no built-in snapshot.
4. **Export from a replica and load into bronze.** Tag every row with the new incarnation and the
   slot's starting position.
5. **Stream from the new slot.**
6. **Sweep.** Some silver rows are still on the old incarnation because the snapshot didn't contain
   them. Those rows were deleted during the gap, so tombstone them.
7. **Rebuild gold** for the affected dates through the normal gate.

**One table only, after a truncate.** The slot is healthy, so skip steps 2–5:
1. Acknowledge the truncate, so the merge can move past it.
2. Trigger a Debezium incremental snapshot of that table. It runs alongside streaming, and one table
   is small enough to go through Kafka.
3. Sweep that table (step 6).

**If it goes wrong.** Gold stays held throughout, so a failed re-snapshot is never visible. Roll
silver back to its Iceberg snapshot from before step 4, and repeat.

## Verification

- `wal_status = reserved`, and slot lag is back under its threshold.
- Silver is within its freshness target.
- After a re-snapshot, the gate reconciles the affected dates against the source's control totals,
  and the version label carries the new incarnation.

## Escalation

- **Slot at risk, or a re-snapshot needed:** the source DBA and the owning service team. The export
  runs from their replica.
- **Vault outage:** the vault owners. The WAL budget is the deadline.
- **Re-snapshot of a money table:** that table's business owner. Gold stays held until the
  re-snapshot completes.
