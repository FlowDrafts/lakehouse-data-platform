# Tasks

The backlog, in a suggested order. Each task names its story, the files it touches, and the test
that proves it is done. Mark a task `[x]` in the same change that completes it.

## Done

- [x] **T01** Partner file versions: register, check, load once, flip by compare-and-set,
  truncation guard (US-1, tests 1.1–1.9)
- [x] **T02** Publish gate: branch, completeness, four measures with fingerprint, pinned
  reference, `fast_forward` (US-2, tests 2.1–2.8)
- [x] **T03** Transaction cut: longest complete prefix, tagged per cut, incremental and rerunnable
  (US-3, tests 3.1–3.5)
- [x] **T04** Ordered merge with incarnation and the large-column placeholder guard (US-4, tests
  C.1–C.6)

## Open

### Partner files (US-1)

- [ ] **T05** Hold dependent gold when a file misses its arrival window.
  Files: `partner_files.py` (an arrival-window check producing `InputStatus`), `contracts/`.
  Done when: test 1.10 passes, and it has a mutation.
- [ ] **T06** Change-only feeds: apply versions strictly in sequence; stop at a gap.
  Files: `partner_files.py`. Done when: test 1.11 passes.
- [ ] **T07** Announce a reference update only after its version is current.
  Files: `partner_files.py`, `pipeline.py`. Done when: test 1.12 passes.

### Publish gate (US-2)

- [ ] **T08** Test that a paise sum overflow fails rather than wraps. Test 2.9.
- [ ] **T09** Readers during a publish see version N or N+1. Test 2.10.
- [ ] **T10** Label intraday versions "checked against silver". Files: `publish_gate.py`. Test 2.11.
- [ ] **T11** Run the gate's checks from a Great Expectations or Soda checkpoint, calling
  `cell_totals` and `compare_totals`. Files: new checkpoint config; `deploy/airflow/dags/`.

### Transaction cut (US-3)

- [ ] **T12** Load exported and snapshot rows (no transaction id) as the base of a new
  incarnation, then sweep rows the snapshot didn't see. Files: `transaction_cut.py`,
  `cdc_merge.py`. Done when: tests M.1–M.2 pass.

### Gold build

- [ ] **T13** Build a gold table from silver read at one cut and one pointer version, writing
  the version label. Files: a new `publishing/gold_build.py`. Done when: a test shows a build
  never mixes two cuts.

### Plumbing (stubs in `pipeline.py`)

- [ ] **T14** `pull_api_incrementally`: raw response first, keyset paging, lookback with
  deduplication, periodic full sweep (US-7).
- [ ] **T15** `load_clickhouse_copy` and `load_aurora_copy`: one whole published version per
  load (US-5, tests S.1, S.5).
- [ ] **T16** `snapshot_ops_sheet`: a version per read; GL mapping changes wait for approval.
- [ ] **T17** `tag_month_end`: tag the published snapshot; kept five years.

### Migration (US-6)

- [ ] **T18** One-time migration: slot first, export from a replica, tag rows with the slot's
  start, stream. Tests M.1–M.3.
