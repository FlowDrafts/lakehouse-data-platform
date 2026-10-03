# ADR-04: Partner and ops files: register, append, then flip a current-version pointer

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-03 |
| **Decision-makers** | Gaurav |
| **Related** | [Design doc](../architecture/lakehouse-design.md) §7.1, §10.1 · [Runbook](../runbooks/partner-files.md) · [ADR-09](09-one-time-migration.md) |

## Context and Problem Statement

Partner and ops files bring in about 500M rows a day, mostly full snapshots per (partner, feed,
posting date), sometimes split into several part files. Partners resend files, send corrections,
send truncated files, get their clocks wrong, and sometimes don't send at all. Two workers can pick up the same file. We must be able to
answer "what did we know on date X" for five years, and only the partner vouches for a file's
content. How should files be loaded so that none of this corrupts silver?

## Decision Drivers

- Duplicates, corrections, crashes and racing workers must never double-count or lose data.
- "As known at" history must cover five years, well beyond snapshot expiry.
- Concurrent partners must not contend with each other.
- A truncated or missing file must be caught before anything uses it.

## Considered Options

| Option | Pros | Cons |
|---|---|---|
| One row-level merge that decides and writes in a single statement | Handles duplicates, corrections and races in one place | All partners for the same date contend for one partition, and the partner's timestamp decides which version wins. Measured: a 10-row load rewrote 30,000 unrelated rows, and six concurrent partners produced 14 commit conflicts |
| Overwrite the partition for each delivery | Simple | History lasts only as long as snapshots are kept (7 days); no protection against races on its own |
| **Register, append, then flip a current-version pointer** (Audit–Balance–Control) | Appends never conflict; the flip is small and atomic; history is a lookup on a small table | Readers must go through the pointer |

## Decision Outcome

Chosen option: **register, append, then flip a current-version pointer**, because appends don't
contend, a compare-and-set flip settles races, and the history of flips gives five years of "as
known at".

1. **Register** each file part on arrival, recording:
   - its file hash, partner, feed, posting date, the partner's sequence number (the version),
     and its part number and part count (the manifest);
   - a state: `STAGED`, `REJECTED`, `DUPLICATE`, `PUBLISHED` or `SUPERSEDED`.

   A part already received, by its bytes or by its place in a version, stops as a duplicate. A
   changed part is a new version with a new sequence number, never a replacement part.
2. **A contract per feed** declares:
   - schema and units;
   - the posting-day cut-off and its timezone;
   - full snapshot or changes only;
   - trailer fields;
   - the arrival window;
   - whether it's a reference file;
   - the truncation threshold;
   - version order, by **sequence number, not timestamp**.
3. **Check the whole part** before writing a row: structure, types (`12.50` is not paise), keys,
   posting date, and the trailer's row count and signed paise total. Adjustments to earlier
   dates arrive as rows posted today; a closed period is never rewritten. A file that fails goes
   to the failed bucket, and nothing is written.
4. **Load** the rows, tagged with the version and file ID, by replacing any rows that already
   carry that file ID. A replace is idempotent, so a rerun after a crash, or two workers racing
   on the same part, loads the rows once (Iceberg rejects the losing commit, and it retries).
5. **Publish by flipping the pointer** for (partner, feed, posting date) to this version, only
   once every part in its manifest is staged, and only if its sequence number is higher.
   - This is a compare-and-set: of two racing workers, exactly one wins.
   - The pointer table is partitioned by partner, so only files for the same delivery contend.
   - Every flip is kept with a valid-from and valid-to time.
6. **Silver is the rows of the current version.**
7. **Change-only feeds** apply strictly in sequence order. A missing sequence number stops that
   feed.
8. **Truncation guard.** If the version has more than the feed's threshold fewer rows than the
   same weekday usually has (the median of the last four weeks), the publish waits for human
   approval. A new feed has no history, so only the independent check covers it.
9. **Independent check**, where an independent record exists: our own ledger, and the bank
   statement matched by payment reference (UTR).
10. **Missing file.** An alert fires when the arrival window closes, and dependent gold tables stay
    held.

**Failed files** are fixed by the partner resending. When an internal fix can't be avoided, it
enters as a new version: the original is kept and the approval is recorded. Files are never edited
by hand.

**Reference fast track.** Some files are small full snapshots that apps use when making a
decision: watchlists, rate cards, operator and plan lists, merchant lists, and the GL mapping.
They go through the same checks, but run as soon as they arrive. After the flip, a "reference X is
now at version N" event goes to Kafka, and Flink and the apps reload.

Any change to the GL mapping needs human approval. A changed mapping moves both sides of a
reconciliation together, so totals still tie while everything downstream is misclassified.

### Consequences

- Readers must go through the pointer. Grants are on silver and its views, never on staging.
- Every version is stored, which is the price of five-year history.
- A truncated file whose trailer matches the truncated content passes the trailer check. Only the
  drift guard and the independent check catch it.
- Not every partner sends sequence numbers. The timestamp fallback requires a timezone on every
  timestamp, and an older-dated file with different content raises an alert.
- A change-only feed stalls on one missing file, by design: a gap is filled, never skipped.
- Nothing is visible until the whole file has been checked.
- Apps must swap reference versions whole.

### Confirmation

Tests 1.1–1.12 in the [test plan](../../tests/README.md).

## More Information

Revisit when a partner moves to streaming delivery; that feed then belongs on the event path.
On-call procedures are in the [runbook](../runbooks/partner-files.md).
