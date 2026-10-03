# Runbook: Publish Gate Hold

| | |
|---|---|
| **Owner** | Data platform on-call |
| **Severity** | Page: any check failed; a hold open for more than 24 hours. Ticket: gold older than its freshness target; publish refused |
| **Last reviewed** | 2026-10-03 |
| **Related** | [ADR-05](../decisions/05-the-publish-gate.md) · [ADR-01](../decisions/01-catalog-and-consistency.md) · [Design doc](../architecture/lakehouse-design.md) §7.3, §10.2 |

**Scope.** This runbook names each failure, how to recognise it and how it is resolved. Exact
commands and environment settings are out of scope for this design ([index](00-runbook-index.md)).

## Overview

Gold is built on a temporary audit branch and checked before it is published
([ADR-05](../decisions/05-the-publish-gate.md)). A hold means main didn't move. Readers keep the
previous version, labelled with its age, so nothing wrong is visible. The cost of a hold is
staleness. The job is to find where the fault is: in the inputs, in our build, or at the source.

## Rules

1. **Never publish a held branch.** A retry always builds a fresh branch. A held branch is kept for
   investigation only, and expires after 14 days.
2. **Never relax a check to make it pass.** The tolerance on money is zero.
3. **Never write to gold's main branch directly.** Every version goes through the gate.
4. **A fault at the source is fixed at the source.** The fix then arrives through the normal path.

## Triage and Resolution

Which check failed tells you the kind of fault. The checkpoint result is in OpenMetadata.

| Symptom | Check | Likely cause | Resolution |
|---|---|---|---|
| Completeness hold: gold older than its target | Which declared input hasn't arrived | A file missing or late; a change stream not yet read past the day's cut-off | Follow that input's runbook ([partner files](partner-files.md), [CDC](cdc-slot-and-resnapshot.md)). The next run publishes once the input arrives. Publish with a declared gap only if the contract marks that input optional |
| Row counts differ | Diff on key | The build drops or adds rows (a filter or join), or a change arrived after the silver version | Fix the build, or wait for the input, then rerun |
| Counts match; paise totals differ | Diff on key and amount | Units (rupees in a paise column), a sign flipped on refunds or reversals, or a rounding step | Fix the transformation, then rerun |
| Counts and totals match; distinct keys differ | Duplicate keys in the branch | A join fanning out on a non-unique key, offset by a dropped row | Fix the join key, then rerun |
| Only the fingerprint differs | Diff on key and amount | Money attributed to the wrong key, through a wrong join key or a swapped key mapping | Treat it as a misattribution, not noise. Fix the mapping, then rerun |
| A sum fails with an overflow | The query error | A unit conversion applied twice, or corrupt amounts | Find the bad rows and fix them upstream. Never widen the type to get past it |
| Silver check passes; the source's totals don't match (closed date) | The source's control totals against silver | Data that never reached silver; the source's totals defined differently from ours; a source correction after close | Missing data: follow the input's runbook. A definition gap: agree it with the source team |
| Publish refused: main moved since the branch was cut | Main's commit history | Two runs of the same build at once, or a manual write | Find the writer, limit the build to one run at a time, then rerun |
| A correction for a date already reconciled, or a month already closed | That date's version label; the month-end tag | A restatement | Rebuild the date through the gate, then reload ClickHouse and Aurora. Leave the month-end tag alone and book the difference in the current month |

## Investigating a Held Branch

1. **Read the checkpoint result:** which check failed, for which business line and date, and both
   values.
2. **Diff the branch against the side it was compared with.**
   - Read the branch through Spark as `<table>.branch_<name>`. Access is on-call only.
   - Use a full outer join on key, and keep rows where the amounts differ or one side is missing.
   - Compare against the silver version recorded in the branch's label, not today's silver, which
     has moved on.
3. **Classify the fault** using the table above, fix it, and rerun. The rerun builds a new branch,
   and the held one is left to expire.

## Verification

- A new version is on main, labelled "reconciled" or "checked against silver" as expected.
- ClickHouse and Aurora have loaded that same version, and their labels match main.
- The hold alerts have cleared.

## Escalation

- **A hold open for more than 24 hours:** the table's business owner. A second alert fires
  automatically.
- **A break traced to the source's control totals:** the source team.
- **A restatement of a closed month:** finance, who own the adjustment.
