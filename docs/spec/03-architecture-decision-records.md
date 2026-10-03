# Plan: rewrite the decision folder as industry-standard ADRs, with a technical review

## Context

The design doc was restructured into an industry-standard technical design document and reviewed
technically. The user wants the same done to `docs/decisions/` (the register plus ADRs 01–09):
1. A standard ADR format.
2. A technical review of each decision, fixing inaccuracies.
3. Remove redundancy and over-expressive phrasing.

The findings are shared first; the edits follow approval. It's docs only, with no code.

**Decided with the user:** ADR-06 stays one record, retitled "Application read paths", with the
store choice as a section inside it. Nothing is renumbered, so all existing links keep working.

## Standard format (MADR-based, applied to all nine ADRs)

```
# ADR-NN: <decision as a title>
| Status | Date | Decision-makers | Related |   ← metadata table
## Context and Problem Statement
## Decision Drivers                  ← 3–4 bullets: the forces that decided it
## Considered Options                ← one table: Option | Pros | Cons (merges MADR's
                                       options list and pros/cons, so nothing is repeated)
## Decision Outcome                  ← "Chosen option: X, because …", then the mechanism
### Consequences                     ← Negative / operational costs (the positives are already
                                       in the chosen option's Pros, so they aren't restated)
### Confirmation                     ← how it's verified: test-plan IDs, or
                                       "(not yet in the test plan)"
## More Information                  ← Revisit when …; related ADRs and design-doc sections
```

- **Metadata:** Status `Accepted`; Date `2026-10-03`; Decision-makers `<your name>` (the same
  placeholder as the design doc); Related links to the design-doc section.
- **Titles:** `ADR-01` … `ADR-09`. Filenames stay as they are.

**Register** (`00-decision-register.md`), restructured as a standard decision log:
- An intro stating the criteria for a full ADR: hard to reverse, has credible alternatives, or
  carries a guarantee the design depends on.
- **Architecture Decision Records:** ID | Decision | Status | Primary cost.
- **Lightweight Decisions:** Area | Decision | Alternatives | Consequence | Revisit when.
- **Open Decisions:** the schema registry, moved out of the main table, with status `Proposed`.

## Technical review findings (each one is fixed in the rewrite)

| ADR | Finding | Fix |
|---|---|---|
| 01 | **Inaccurate absolute claim.** "No catalog except Nessie commits several tables atomically." The Iceberg REST spec defines a multi-table commit endpoint, and some catalogs implement it. | Restate what's verifiable: Glue commits per table, and **Spark's writers commit one table per write**. A cross-table publish isn't available to our jobs without custom code, whatever the catalog supports. Nessie is the mature option for catalog-wide branches and commits |
| 01 | "every answer returns it" is too broad, since money comes from the source | "every answer served from the lake" (matches the design doc) |
| 02 | **Erasure gap.** Deleting a vault entry doesn't erase anything that survives in **vault backups**: the wrapped per-customer key could be restored | Vault key-store backups expire within a stated erasure window. Erasure is complete once the last backup holding the key ages out |
| 02 | "hard cap" on replication-slot lag is vague | Name it: `max_slot_wal_keep_size`. Exceeding it invalidates the slot and forces a re-snapshot (ADR-03) |
| 03 | Status line carries history ("reverses an earlier choice…") the reader never saw | Remove. The rejected option is already in the options table |
| 03 | "Each guard exists because a real Iceberg run broke without it" is history, not a reason | Replace with: each guard is covered by a test that fails if it's removed (mutation testing) |
| 03 | **Missing: idle sources.** A low-traffic database never advances its slot, so WAL accumulates and the completeness cut-off never passes | Add Debezium heartbeats (`heartbeat.interval.ms`) to the settings list. Matches design doc 7.3 |
| 03 | "Spark reads new bronze snapshots" is imprecise | "reads the changes between bronze snapshots incrementally" |
| 04 | **Contention gap.** If the current-version pointer is one small unpartitioned Iceberg table, flips for *different* partners rewrite the same file and conflict. That contradicts "appends never conflict" | The pointer table is **partitioned by partner**, so only files for the same delivery contend |
| 04 | "beyond a threshold" leaves the truncation threshold undefined | The threshold is set per feed in its contract |
| 04 | "Our earlier version of this rewrote 30,000 rows…" refers to history | Reword as measured evidence: "Measured: a 10-row load rewrote 30,000 unrelated rows; six concurrent partners produced 14 commit conflicts" |
| 05 | "Nothing unchecked is ever readable" is too broad | "No unchecked gold version is ever readable" |
| 05 | **Missing feasibility detail.** The fingerprint has to be computed *identically* on the source (Postgres) and in the lake (Spark) | State it: the same hash and truncation on both sides. Also state that the checkpoint reads the branch through Spark (`<table>.branch_<name>`) |
| 06 | Retitle as one decision with two parts (user decision) | "Application read paths: money from the owning service, derived data from Aurora" |
| 06 | **Missing operational cost.** A swap by rename takes a brief exclusive lock, so it waits for in-flight reads | Add: set `lock_timeout` on the swap and retry |
| 06 | "ClickHouse is built for a few heavy scans, not 50M customers…" is rhetorical | "Optimised for analytical scans; high-concurrency point lookups aren't its strength, and sharing it with BI couples app latency to dashboards" |
| 07 | "loaded whole" doesn't say how | Load into a staging table, then `EXCHANGE TABLES`, an atomic swap, so dashboards never see a partial load |
| 07 | "refresh when a new version publishes" is imprecise | Cube's `refresh_key` is bound to the published version |
| 08 | **Missing delivery semantics** for a lane serving money-adjacent signals | Flink checkpoints with an exactly-once Kafka sink (transactional producer), consumers read `read_committed`, and events are deduplicated on `event_id` |
| 08 | "so neither can take the other down" overclaims | "a slow or failed app never back-pressures Flink, and apps can replay the topic" |
| 08 | The heading "What it costs, plainly" and the phrase "…or it becomes a trust problem" are over-expressive | The standard "Consequences" heading, with the line trimmed |
| 09 | **Inaccurate claim of exactness.** An RDS snapshot export can't be taken *exactly* at the slot's position | Take the export after the slot exists, and tag its rows with the slot's starting position. Changes captured in both are re-applied by the stream in order, so the final state is correct. What must never happen is tagging the export *later* than its true state |
| Register | "Revisit if: Never; …" (Layers) is over-expressive | "—" |
| Register | Metrics row: VictoriaMetrics *replaces* Prometheus storage, so "one more component" is wrong | "Prometheus-compatible; long-term storage" / cost "less widely used than Prometheus" |
| Register | The "Held branches" and "Failed files" rows duplicate ADR-05 and ADR-04 | Remove both rows |
| Register | The Kafka settings row duplicates ADR-03 | Keep only what isn't in ADR-03 (events partitioned by `customer_id`; ~540 partitions for consumer parallelism), and point to ADR-03 for the rest |
| Register | The partitioning row says ">200,000 files a day" with no unit | "per table" (matches the design doc) |
| Register | Region row: "Revisit if: Before go-live" is a deadline, not a trigger | "Build and rehearse before go-live" |
| Register | Testing row: "a suite that deletes each guard in turn" | "mutation testing" (matches the design doc) |

**Applied everywhere:** remove history and journey wording; one decision per section; consistent
terms with the design doc (version label, gate, held branch, current-version pointer, mutation
testing).

## Confirmation mapping (test-plan IDs that already exist)

| ADR | Confirmed by |
|---|---|
| 01 | 2.10, 3.2, 3.4 |
| 02 | (not yet in the test plan) a seeded canary personal value must never appear in clear in Kafka or bronze; a CI check that every contract column is classified |
| 03 | The "Also covered" CDC guard table; M.1, M.2 |
| 04 | 1.1–1.13 |
| 05 | 2.1–2.11 |
| 06 | 3.1, 3.2, 3.6 |
| 07 | 3.4, 3.5 |
| 08 | 3.3; the daily drift job (not yet in the test plan) |
| 09 | M.1–M.3 |

## Files

- **Rewrite:** `docs/decisions/00-decision-register.md` and `01`–`09` (each read first). The
  filenames don't change.
- **Design doc** (`docs/architecture/lakehouse-design.md`): no structural change. The links stay
  valid because there's no renumbering. Only check consistency: ADR-04's partner-partitioned
  pointer and ADR-09's "tag with the slot position" wording must agree with design-doc sections
  7.2 and 10.1. Adjust a phrase only if they contradict.
- **No change:** the test plan and the runbook.

## Verification

1. A link check across `docs/**/*.md` and `tests/test-plan.md`: zero broken.
2. Every ADR has the same heading set, checked by grep for the 7 standard headings in each file.
3. `grep` confirms the removed phrases are gone: "reverses an earlier", "because a real Iceberg
   run broke", "Our earlier version", "plainly", "trust problem", "Never; the strictness",
   "Held branches |", "Failed files |", "one more component".
4. Every Confirmation test ID exists in `tests/test-plan.md`.
5. Re-read ADR-01, 02, 04, 09 to confirm each technical fix is stated precisely and matches the
   design doc.
