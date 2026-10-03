# Independent review: the repo against the brief, the architecture and the code

## Context

The user asked for an independent scan of the whole repo, compared against the brief, covering
the architecture and the implementation, repeated until no new findings appear. Four passes ran:

1. **The brief's deliverables and questions**, checked against the repo.
2. **Code review**, as the brief's reviewers would read it ("we read code as code").
3. **Consistency** between the docs, the deploy and DDL samples, CI, Docker and git.
4. **The brief's evaluation criteria.** This pass added nothing new, so the review converged.

Everything was read-only. The findings below are ranked by impact, and each has a proposed fix.

## Blockers: fix before submitting

| # | Finding | Evidence | Proposed fix |
|---|---|---|---|
| B1 | **Nothing is committed.** A clone gets commit `5dbe448`: the old design, old code and the old `brief/` folder | `git status`: every change this session is uncommitted | Commit, after the fixes below |
| B2 | **The Docker build will fail.** `.dockerignore` excludes `*.md`, but the Dockerfile runs `COPY pyproject.toml README.md ./`. That breaks the CI `docker` job and the Docker route documented in the READMEs | `.dockerignore` line `*.md`; Dockerfile `COPY ... README.md`. Reasoned, not run: Docker isn't installed here | Add `!README.md` to `.dockerignore`, or drop `README.md` from the COPY. Also align the image to JDK 21 (it uses 17; local and CI use 21) |

## High: code defects a reviewer would catch (tests pass, but the guarantee doesn't hold at scale or under concurrency)

| # | Finding | Why it matters | Proposed fix |
|---|---|---|---|
| H1 | **The transaction cut scans all of bronze on every run.** `_landed_event_counts` groups the *entire* bronze table per source table and collects every transaction ID to the driver; `advance_to_cut` joins the whole of bronze | At 10k events/s, bronze holds hundreds of millions of transactions within days, so the driver runs out of memory and each run rescans five years. It fails exactly where the brief's scale applies | Count only transactions after the previous cut (join with the new END records), and read only bronze appended since the last cut (ingest-time window) |
| H2 | **The cut isn't safe to rerun.** Tags are created per table with `CREATE TAG`. If a run dies after tagging `loan` but before `ledger_entry`, the rerun fails because the tag already exists | The CDC runbook says "restart and it resumes". Here it wouldn't | `CREATE TAG IF NOT EXISTS`, plus a test that reruns after a partial run |
| H3 | **Two workers receiving the same part can append it twice.** `append()` checks the snapshot marker, then writes: a check-then-act race. The racing test covers only `publish` | The same rows counted twice under one version, which is exactly the failure #1 claims to prevent | Make the append idempotent and conflict-detected: replace by file (`overwrite(file_id = X)`) instead of append-if-absent. Add a racing-receive test and a mutation |
| H4 | **SQL is built by pasting partner-supplied values into strings** (`partner`, `feed`, `file_id`, `reason`) in `partner_files.py` | A quote in a partner or file name breaks the SQL, or injects into it. Reviewers flag this immediately | Validate these identifiers against a strict pattern when a `FilePart` is created, and escape free text (`reason`) |

## Medium: consistency and brief-fit

| # | Finding | Proposed fix |
|---|---|---|
| M1 | **Over the code budget.** The hard parts are 436 lines of real code (254 in `partner_files.py`); the brief says roughly 200–400 | Trim `partner_files.py`: fold the register bookkeeping helpers, and simplify state updates. Target ≤ 400 in total |
| M2 | **The brief asks "Where does this design break first?"** The design doc never answers it directly (only risk 1, and the tests README) | Add a short explicit answer to §9 or §12: merge throughput and delete files at peak first, then the cut waiting on the slowest partition |
| M3 | **The design doc is about 6.6 pages**, against 4–6 | Trim §4, §6 and §7 (already-reviewed sections) by about 300 words |
| M4 | **Deploy and DDL gaps for the cut.** Bronze `position` and `kafka_offset` need sink-side Kafka metadata, but there's no Iceberg sink sample. The Debezium `InsertField` adds `source_incarnation` as a *string*, while the DDL says `INT` | Add a short Iceberg sink `KafkaConnector` sample (append-only, with `InsertField` adding offset and partition). Cast the incarnation, or make the column a string |
| M5 | **The runbook index has no alert for "transaction cut not advancing"**, though the CDC runbook has the row | Add the alert row (Page) |
| M6 | **`publish_or_hold` reports a failure after a successful publish** if `DROP BRANCH` fails after `fast_forward` | Treat the drop as best-effort (log it, return published) |
| M7 | **Ruff version drift.** CI pins ruff 0.14.2, but local dev installs the latest (0.16 in the fresh clone), so formatting can differ and turn CI red | Pin `ruff==0.14.2` in `pyproject.toml` dev dependencies |

## Low

- The README and test plan hard-code "26 tests" and "18 mutations", which will drift. Acceptable
  for a submission.
- No CI badge until the repo has a remote.
- The gold build itself (reading silver at the cut) isn't in code; the gate takes the build's rows.
  This is already stated in the docs.

## What holds up well (no change)

- Every brief deliverable is present:
  - design document;
  - diagram, as a PNG plus editable draw.io;
  - real code for 3 hard parts;
  - a test plan with tests as code;
  - an honesty section.
- The brief's sections (architecture, getting data in, trust, serving, living with it, cost,
  assumptions, scale) all map to design sections.
- Tests run on a real Iceberg engine, mutation testing catches 18 of 18, and a fresh copy sets up
  and runs.

## Proposed order of fixes (on approval)

1. **H1–H4 code fixes, each with a test**, plus mutations for H2 and H3.
2. **M1:** trim to budget.
3. **B2, M4–M7.**
4. **M2, M3:** docs.
5. Re-run tests, mutation testing, the demo, lint and the link check.
6. B1 (commit) only when the user asks.

## Verification

- `pytest`: all pass, including the new racing-receive and cut-rerun tests.
- Mutation testing: all caught, including the new entries.
- A line count of the hard parts ≤ 400.
- The demo still runs.
- `.dockerignore` versus the Dockerfile COPY lines checked by script (Docker isn't available
  locally).
- The link check is clean.

---

*One row of the blockers table (B3) is omitted from this copy: it concerned placeholder names and the history of a private working repository, not the design or the code.*
