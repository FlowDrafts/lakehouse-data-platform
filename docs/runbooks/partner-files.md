# Runbook: Partner and Ops Files

| | |
|---|---|
| **Owner** | Data platform on-call |
| **Severity** | Page: a file missing, or held by the truncation guard, for a money feed or a watchlist. Ticket: everything else |
| **Last reviewed** | 2026-10-03 |
| **Related** | [ADR-04](../decisions/04-partner-and-ops-files.md) · [ADR-09](../decisions/09-one-time-migration.md) · [Design doc](../architecture/lakehouse-design.md) §7.1, §10.1 |

**Scope.** This runbook names each failure, how to recognise it and how it is resolved. Exact
commands and environment settings are out of scope for this design ([index](00-runbook-index.md)).

## Overview

Each file goes through four steps ([ADR-04](../decisions/04-partner-and-ops-files.md)):
1. It is registered on arrival.
2. It is checked whole.
3. Its rows are appended.
4. Its version is published, once every part in the manifest is in, by flipping the
   current-version pointer for (partner, feed, posting date).

A file that fails changes nothing, and the previous version stays current. The risk is a missing or
held file, which holds the gold tables that depend on it. For a watchlist, a stale list is a
regulatory exposure, not just a data delay.

## File States

The register is the first place to look.

| State | Meaning |
|---|---|
| `STAGED` | Checked and appended, but its version isn't published yet: parts still missing, held by the truncation guard, or waiting to run |
| `REJECTED` | Failed a check and nothing was written. The file is in the failed bucket, with the reason in the register |
| `DUPLICATE` | The same bytes, or the same part of the same version, were already received. Nothing was done |
| `PUBLISHED` | Its version is the current one |
| `SUPERSEDED` | A newer version is current |

## Rules

1. **Never edit a file by hand.** Its hash changes, and the record of what the partner actually
   sent is lost. An internal fix enters as a new version: the original is kept and the approval
   recorded.
2. **Never write to staging or silver directly.** Every change goes through the pointer.
3. **Roll back by flipping the pointer back.** It's one row, takes effect at once, and loses
   nothing.

## Triage and Resolution

| Symptom | Check | Likely cause | Resolution |
|---|---|---|---|
| The partner says they sent it; nothing is registered | The landing-zone listing for that partner and date | It never arrived, or it landed at the wrong path or under the wrong name | Ask for a resend, or move the file to the right path. It registers on arrival |
| `REJECTED` | The reason in the register | A trailer mismatch, a schema change, wrong units, or a posting date out of range | The partner resends. An override needs recorded approval, and enters as a new version |
| `DUPLICATE` | — | The partner retried | Nothing to do |
| A correction arrived, but the numbers didn't change | The new file shows `SUPERSEDED` | Its sequence number isn't higher than the current file's | Confirm with the partner. They resend with a higher sequence number, or an approved override enters as a new version |
| Truncation guard hold | The version's row count against the same weekday in recent weeks | A file cut off partway, whose trailer matches what was sent | Keep the hold and ask the partner. Approve only once they confirm the drop is real |
| `STAGED`, not `PUBLISHED` | The register, for the version's other parts | A part is still missing, or the job died before publishing | Wait for the missing part, or re-run. Both receiving and publishing are safe to repeat: a part is never loaded twice |
| Commit conflicts or a slow load | Airflow's run history | Two runs of the same job at once. Files for different deliveries don't contend | Limit the job to one run at a time |
| Missing-file alert; gold held | The feed's arrival window | The partner is late, or has failed | Chase the partner. Publish with a declared gap only if the contract marks the feed optional |
| A change-only feed has stopped | The register, for the missing sequence number | One file in the sequence never arrived | Get the missing file. Never skip a sequence number |
| A correction for a month already closed | The register; the month-end tag | A restatement | Publish the correction as usual, then follow the restatement row in the [publish gate runbook](publish-gate-held.md) |
| Schema check fails after the layout changed | The register | Contract drift | Agree a new contract version. **Never auto-adapt schemas for files that carry money** |
| A GL mapping change is waiting for approval | The approval queue | A routine edit by Ops | Check it before approving. A wrong mapping moves both sides of a reconciliation together, so totals still tie while everything downstream is misclassified |
| A reference file published, but apps still use the old one | The "reference updated" event; the app's reload log | The event wasn't consumed, or the app's reload failed | Re-publish the event. Apps load the new version whole before switching. An announcement before the pointer flips is a bug |

## Verification

- The register shows the file as `PUBLISHED`, and the pointer's history shows the flip.
- Silver's row count and paise total for that file equal its trailer.
- Dependent gold tables publish on their next run.
- For a reference file, apps report the new version.

## Escalation

- **A money feed held for more than 24 hours:** the business owner of that feed.
- **A watchlist held for any length of time:** risk and compliance.
- **The same partner rejected three times in a week:** their account manager, about the contract.
