# Plan: identify the genuine hard problems from first principles, then decide code and tests

## Context

The user rejected the earlier analysis because it started from our design. This pass starts from
the **sources**:
- Postgres change data capture;
- app event streams;
- partner and vendor files;
- third-party APIs;
- Ops spreadsheets.

It lists every way each source misbehaves, scores each scenario against a strict test, and
challenges the shortlist over several passes until the choice holds. The result is two genuine
hard problems and one hidden one. Code and tests are then decided from those three.

## The test a problem must pass (all five)

1. **Inevitable.** It happens in normal operation at this scale, not as a rare fault.
2. **Silent.** It produces a plausible wrong number that passes the checks a competent team would
   naturally build.
3. **Not solved by a tool or a setting.** It needs design and code whose correctness isn't
   obvious.
4. **Trust impact.** It affects numbers that finance, auditors or apps rely on.
5. **Has a codeable core.** A guarantee that holds or doesn't, in roughly 100–200 lines.

## Pass 1: every scenario, by source

### Partner and vendor files (500M rows/day, settlements, money)

| # | Scenario | What goes wrong silently |
|---|---|---|
| F1 | The exact same file sent twice | Rows counted twice |
| F2 | Same content, different bytes (regenerated, re-sorted, recompressed) | Looks like a new file; additive handling double-counts |
| F3 | A correction replacing an earlier version | Loads alongside the original; both tie to their own trailers |
| F4 | An older version arriving after a newer one | The stale version becomes current |
| F5 | **One day split into N part files, arriving over hours, with parts re-sent** | Parts of v1 and v2 mixed into one "day". Each part ties to its own trailer |
| F6 | A file truncated, with a trailer that matches the truncated content | Half a day (or half a watchlist) published |
| F7 | A file that never arrives | A short day looks like a quiet day |
| F8 | Full snapshot vs changes only vs month-to-date, misread | A delta treated as a full replacement deletes rows; a month-to-date file treated as daily double-counts |
| F9 | Adjustments to earlier dates inside today's file | Rejected as "wrong date", or rewrites a closed period |
| F10 | The partner's clock is wrong, or its sequence numbers restart | Ordering by time or number goes wrong; the feed silently stalls |
| F11 | Layout or units change (rupees to paise, column order) | Wrong but numeric values |
| F12 | Two workers pick up the same file | Double load, or a lost update |

### Postgres CDC (10k events/s across lending, insurance, recharge)

| # | Scenario | What goes wrong silently |
|---|---|---|
| C1 | Duplicates from connector restarts (at-least-once delivery) | Replays applied again |
| C2 | One key's events out of order (replay, re-snapshot overlap, a change in partition count, primary-key updates) | A newer row regressed to an older state |
| C3 | A delete arriving before its insert, or an older update arriving after a delete | A deleted row comes back |
| C4 | Truncate | Nulls written over real values |
| C5 | **One transaction across several tables (loan + ledger lines), split across topics and partitions** | Gold reads the loan without its ledger lines (a torn read), and it ties to silver |
| C6 | "Is the day complete?" when partitions are idle or behind | Can't tell idle from lagging, so a short day publishes |
| C7 | **Unchanged large (TOAST) columns arrive as a placeholder value in updates** | A naive merge overwrites real JSON or text with `__debezium_unavailable_value` |
| C8 | The source purges old rows (retention or archival jobs), which arrive as deletes | Lake history disappears; past gold changes when rebuilt |
| C9 | A late-committing or backdated transaction for a closed date | A closed period changes silently |
| C10 | Database restore or failover | Positions reset, or the slot is lost |
| C11 | A table with no primary key | Can't be merged |

### App event streams (not money)

| # | Scenario | What goes wrong silently |
|---|---|---|
| E1 | Client retries (duplicates) | Inflated counts. Deduplicating across 5 years is expensive; deduplicating within a window misses late duplicates |
| E2 | Offline devices sending events days late | Closed dates change |
| E3 | Device clocks skewed | Events in the future or the wrong day |
| E4 | Events dropped on the client | No source of truth to reconcile against |

### Third-party APIs (payment gateway and recharge-operator status, credit bureau, KYC)

| # | Scenario | What goes wrong silently |
|---|---|---|
| A1 | **Incremental pull with an `updated_since` watermark, where records become visible after their `updated_at` (provider lag), or share a timestamp at the boundary** | Records missed **forever**. The watermark has moved past them |
| A2 | Offset pagination over data that changes during the pull | Records skipped or duplicated between pages |
| A3 | Rate limits, or timeouts mid-pagination | A partial pull recorded as complete |
| A4 | `200 OK` with an empty or partial body | Looks like "nothing changed" |
| A5 | The provider corrects history without changing `updated_at` | Never picked up |
| A6 | Retrying a request that isn't idempotent | Side effects, duplicates |
| A7 | No completeness signal at all (no trailer, no counts) | Nothing to reconcile against |

### Ops spreadsheets

| # | Scenario | What goes wrong silently |
|---|---|---|
| S1 | A GL mapping or fee table edited retroactively | Both sides of a reconciliation move together: totals tie, everything is misclassified |
| S2 | Edited mid-read; formula errors; free text | A partial or wrong reference |

### Across sources

| # | Scenario |
|---|---|
| X1 | Business-day cut-offs differ by source (IST vs partner cut-off), so day boundaries don't line up |
| X2 | The same transaction reported by the database, the partner file and the bank statement: many-to-one matching, net of fees |
| X3 | Corrections after a period has closed (restatement) |

## Pass 2: score against the test (✓ meets, ~ partly, ✗ no)

| Scenario | 1 Inevitable | 2 Silent | 3 No tool fixes it | 4 Trust | 5 Codeable | Verdict |
|---|---|---|---|---|---|---|
| F1–F6, F10, F12 (which version of a delivery is the truth) | ✓ | ✓ | ✓ | ✓ | ✓ | **Genuine** |
| F7 (missing file) | ✓ | ✓ | ✓ | ✓ | ✓ | Part of completeness |
| F8, F9, F11 | ✓ | ✓ | ~ (declared in the contract) | ✓ | ~ | Handled by the contract |
| C1–C4 (one key out of order, duplicates, deletes) | ✓ | ✓ | **✗** (a merge ordered by change-log position is documented standard practice) | ✓ | ✓ | **Baseline, not a hard problem** |
| C5 + C6 (cross-table consistency and completeness) | ✓ | ✓✓ (ties to silver) | ✓ (no tool does it across Iceberg tables; Glue commits per table) | ✓ | ✓ | **Genuine, and hidden** |
| C7 (TOAST placeholder) | ~ (only tables with large columns) | ✓ | ~ (`REPLICA IDENTITY FULL`, or a merge guard) | ~ (not money) | ✓ | A baseline guard: one merge clause |
| C8 (purge vs business delete) | ~ | ✓ | ~ (a source-side convention) | ✓ | ✗ | Named limit, plus a convention |
| C9, X3 (restatement) | ✓ | ✓ | ✓ | ✓✓ | ✗ (bitemporal gold is far too big) | Named as the biggest thing not solved |
| E1–E4 | ✓ | ✓ | ~ | ✗ (events carry no money here) | ✓ | Design: labelled, never money |
| A1, A2, A5 (incremental extraction) | ✓ | ✓✓ (the loss is permanent) | ~ (known discipline: lookback, keyset pagination, a periodic full sweep) | ~ (caught at close by the operator's settlement file) | ✓ | **Strong; tested in Pass 3** |
| A3, A4, A6, A7 | ✓ | ✓ | ~ | ~ | ~ | Extraction discipline |
| S1 (reference edits) | ~ | ✓✓ | ~ (versioning plus human approval) | ✓ | ~ | Design control (in place) |
| X1, X2 (matching across sources) | ✓ | ✓ | ✓ | ✓ | ✗ (a matching engine is a product in itself) | Named limit |
| "Publish only verified data" | — | — | — | — | — | Not a source problem. It's the **answer** to completeness and correctness. Tested in Pass 3 |

## Pass 3: challenge the shortlist

**1. "Out-of-order events in CDC" is not the hard problem; ordering *across* keys and tables is.**

Within one key, order is lost only in known ways: replays, re-snapshot overlap, a change in
partition count, primary-key updates. A merge that applies a change only if its change-log
position is newer, stores deletes as tombstones and fails on truncate fixes all of them. That's
documented practice, and an interviewer will see it as baseline. It stays as code (it's
mandatory, and the tests are cheap), plus two guards found in Pass 1:
- the TOAST placeholder (C7);
- the incarnation for restore (C10).

What no tool fixes is consistency **across tables** in one transaction, and knowing a day is
**complete** across about 36 partitions where idle and lagging look identical (C5 + C6). It's
also silent in the worst way: gold ties to silver because silver itself is torn. The previous
code's epoch heuristic declared exactly this state complete, which is evidence that it's hard to
see. **→ The hidden problem.**

**2. Files are genuine, and the hard core is "what does this delivery replace, and is it whole?"**

F1–F6 and F10 are all one question. A delivery can be:
- a duplicate;
- a re-generation;
- a new version;
- one part of N;
- an older version arriving late;
- truncated.

Only the partner vouches for it. F5, multi-part with mixed versions, is the sharpest case: every
part ties to its own trailer while the "day" mixes v1 and v2. F9 is settled by an accounting
principle rather than code: a file reports its **posting date**, and corrections to earlier dates
arrive as adjustment rows posted today. Closed periods are never rewritten. **→ Genuine #1.**

**3. APIs: genuinely dangerous, but the fix is standard discipline, and the money is caught
elsewhere.**

A1 is the most silent loss anywhere on the list: once the watermark moves past a record, nothing
ever looks for it again. But the fix is known extraction discipline:
- save the raw response first;
- use keyset pagination;
- re-read a lookback window each pull and deduplicate;
- run a periodic full sweep, or check against a count endpoint.

The money effect (a recharge status, a payment status) is also caught at close by the operator's
or gateway's own settlement file, which is a partner file. So it fails test 3 and only partly
meets test 4. It becomes a short design section and a named limit, not a deep dive. Its real
residue, **"an API gives no completeness signal"**, feeds the next problem.

**4. "Verified before visible" is genuine once it's framed as a problem, not a mechanism.**

The brief asks it directly ("how does someone know a table is correct and complete?"). On its own
it's the obvious question. What makes it hard here is that **each source proves completeness
differently, or not at all**:

| Source | Completeness signal |
|---|---|
| Files | Arrival calendar plus parts manifest |
| CDC | The transaction cut (problem #3) |
| APIs | None: a full sweep or count, or labelled unverifiable |
| Events | None, so events never feed money |

Correctness is also hard because the source moves while we compare:
- compare against pinned silver intraday, and against source totals once a date closes;
- add a fingerprint for money moved between keys;
- compute that fingerprint identically in Postgres and Spark.

**→ Genuine #2: "completeness and correctness at zero tolerance, when every source proves
completeness differently and keeps moving."**

**5. Final check for overlap and coverage.**
- #1 owns *which version is the truth* for files.
- #3 owns *a consistent, complete point* for CDC.
- #2 *consumes* both signals, and owns comparing and publishing.

No overlap. Every source family is covered: files → #1/#2, CDC → baseline/#3/#2, APIs → #2
(completeness) plus design, events and spreadsheets → design controls. The three things left
unsolved are named: restatement (C9/X3), matching across sources (X1/X2) and purges (C8). I'm
satisfied with this set.

## The three problems

### Genuine #1: Partner files: which version of a delivery is the truth, and is it whole?

**Guarantee:**
- exactly one current version per delivery;
- an older version never wins;
- a part-set mixing versions never publishes;
- no file is loaded twice, even after a crash;
- a truncated file is held;
- "as known at" works for any past moment.

**Mechanism:**
1. Register each file on arrival.
2. Identify by content, not bytes: a delivery is (partner, feed, posting date). A version is the
   partner's sequence number, and parts are listed in a manifest.
3. Check each part, and **assemble the version only when every part in the manifest is present
   and comes from the same version**.
4. Append idempotently: the `file_id` marker rides in the same commit as the rows.
5. Flip the pointer by compare-and-set, strictly newer only.
6. Truncation guard against a weekday baseline.
7. Missing-file alert when the arrival window closes.

### Genuine #2: completeness and correctness at zero tolerance

**Guarantee:** no gold version becomes readable unless:
- every declared input has proven itself complete by **its own source's signal**;
- it ties exactly (count, signed paise, distinct keys, fingerprint) to the pinned side.

**Mechanism:**
1. Each source type plugs in its own completeness signal.
2. Totals are computed on the branch.
3. The comparison is pinned: silver at the snapshots recorded in the label intraday, and source
   totals once a date closes.
4. Full outer compare.
5. The fingerprint is defined identically for Postgres and Spark.
6. The version label is a per-write property.
7. `fast_forward`, or hold.

### Hidden #3: a consistent, complete cut across one CDC source

**Guarantee:**
- gold never reads a transaction half-applied across tables;
- a business date counts as complete only when every transaction up to its cut-off is in
  silver, for every table of that source.

**Mechanism:**
1. Debezium transaction metadata, on a one-partition transaction topic, with per-table event
   counts.
2. The cut is the longest prefix of fully-landed transactions.
3. The merge applies only rows inside the cut, and stamps `cut.<source>` on each commit.
4. Gold resolves every input at the same cut.
5. Heartbeats keep an idle source's cut moving.
6. Exported and snapshot rows count as cut 0 of their incarnation.

### Baseline (code, but not a hard problem): the CDC merge

The existing four guards, plus:
- ordering by (incarnation, change-log position);
- a TOAST-placeholder guard: never write the placeholder over a real value.

## What this changes downstream

| Area | Change |
|---|---|
| Code | `ingest/files.py` rewritten for #1 (manifest-based assembly, a marker for idempotent append, compare-and-set flip, truncation baseline). `verify/gate.py` rewritten for #2, with a completeness interface per source. New `ingest/cut.py` for #3. `ingest/cdc.py` keeps the merge, adds incarnation and the TOAST guard, and drops epochs. Delete `serve/`. `types.py` shrinks; `pipeline.py` becomes plain stubs. About 400 lines across the three hard parts |
| Tests (real Iceberg plus mutation testing) | #1: mixed-version part-set held; truncated file held; late older version loses; racing workers; crash then rerun with no duplicates; "as known at". #2: money moved between keys; missing input holds only its dependent tables; pinned silver means no false break; fingerprint parity; a cell on one side only; an empty date; main moved. #3: a partition behind keeps its transaction out of the cut; prefix rule; reading at the cut never tears where "latest" does; idle source; cut-off completeness. Baseline: the existing merge tests, plus TOAST and incarnation |
| Docs | Design §10 rewritten around these three, with how they were chosen (this analysis, condensed). §7.1 gains API extraction discipline and the posting-date rule for files. §14 names restatement, matching across sources and purges as unsolved. Test plan rewritten to match. New ADR-10 (the consistent cut). ADR-04 gains manifests and posting dates. The deploy sample adds transaction metadata. DDL changes for the register and bronze |

## Engineering standards (the user's requirement: readable by them and by reviewers)

**Code**
- Python 3.12+. PEP 8, enforced by ruff with the existing rules. Type hints on every public
  function.
- Names say what the thing is, in domain language. No internal jargon ("epoch", "certificate",
  "quarantine").
- Small functions, one job each.
- Docstrings of 2–4 lines: the guarantee, and why it holds. No history.
- SQL built in one place per module, readable, with parameters named.

**Layout, with standard, self-explanatory module names**
```
src/lakehouse/
├── ingestion/
│   ├── partner_files.py      hard problem #1
│   ├── cdc_merge.py          baseline: the ordered merge
│   └── transaction_cut.py    hard problem #3 (hidden)
├── publishing/
│   └── publish_gate.py       hard problem #2 (completeness, fingerprint, publish or hold)
├── models.py                 small shared dataclasses (replaces types.py)
└── pipeline.py               stubs for the surrounding plumbing
```
- The old `ingest/`, `verify/` and `serve/` packages are removed.

**Tests:** major cases only, about 20 in total.
```
tests/
├── README.md                 how to set up and run the tests, mutation testing, the contract check and the demo
├── fixtures/
│   └── iceberg_session.py    the local Spark + Iceberg session and shared builders
│                             (replaces conftest.py; pytest's fixed name, swapped for a logical one)
├── test_partner_files.py     about 6
├── test_publish_gate.py      about 6
├── test_transaction_cut.py   about 5
├── test_cdc_merge.py         about 4 (existing engine tests, kept)
├── mutation/run.py           mutation testing (renamed from breakages/)
└── contract_check.py         Cube filters vs contract validValues (replaces contract_lint.py)
```
- Test names read as behaviour, for example
  `test_older_version_arriving_late_never_becomes_current`.
- Each test sets up (arrange), runs (act), then asserts, in clear separate blocks. Shared builders
  live in `tests/fixtures/iceberg_session.py`.
- **Why not `conftest.py`:** pytest automatically finds fixtures only in files with that exact
  name. Instead, the fixtures module is registered as a pytest plugin in `pyproject.toml`
  (`addopts = "-p tests.fixtures.iceberg_session"`, with `pythonpath = ["."]`). That's a standard
  pytest mechanism, and it keeps a self-explanatory filename.

## Runnable (required)

- `make setup && make test` passes locally on a real Iceberg engine, and the result is shown to
  the user.
- `python tests/mutation/run.py` catches every mutation.
- `python demo/run.py` is rewritten as one short scenario per hard problem, and is run.
- `pyproject.toml` drops `pydantic` (the semantic validator is gone), and registers the fixtures
  plugin.
- **`tests/README.md` documents how to run everything.** It's short:
  - prerequisites: `make setup`, which installs JDK 21, the Iceberg jar and the virtualenv under
    `.tools/`;
  - the commands: `make test` (with the fast-only variant), `make mutation`, `make demo`, and the
    contract check;
  - one row per test file: which hard problem it covers, and the test-plan IDs.

  The root README links to it rather than repeating it.

## References updated in every folder (after the code passes)

- **Root `README.md`:** rewritten for the current layout and commands. That also fixes the 8
  broken links.
- **`docs/`:**
  - design §10, §11 and §14;
  - `tests/test-plan.md` (IDs mapped to the real test names);
  - ADR-03 and ADR-04, a new ADR-10, and the decision register;
  - runbooks that name code paths.
- **`contracts/`, `deploy/` and `tables/` READMEs and samples:** module paths; transaction
  metadata in the Debezium sample; DDL changes.
- **`.github/workflows/ci.yml`:** new test and mutation paths, and `contract_check.py`.
- **`Makefile`:** remove the stale `diagram` target; add `demo` and `mutation` targets.
- **`Dockerfile`:** copies the new paths.
- **Final sweep:** a grep for every old path (`ingest/`, `verify/`, `serve/`, `breakages`,
  `contract_lint`, `types.py`) across the repo returns nothing, and the link check passes.

## Order of work

1. Docs.
2. Code: the hard parts first.
3. Tests: the hardest first, then the breakages catalogue.

## Verification

- `make test` against a real Iceberg engine.
- `tests/breakages/run.py`: every guard's mutation must be caught.
- ruff.
- A line count against the ~400-line budget.
- The doc link check.
- A grep confirming no "epoch", "publish_registry", "quarantine" or semantic-validator references
  remain.
