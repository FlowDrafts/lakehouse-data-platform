# Tests and Test Plan

The tests for the three hard problems in the [design](../docs/architecture/lakehouse-design.md)
(§10): how to run them, what each one asserts, and **what the system would get wrong if the
design were wrong**. They run against a real local Spark and Iceberg engine, not mocks.

## Running the Tests

### Setup

You need Linux, macOS or WSL, with `curl` and `make` (on Ubuntu or WSL: `sudo apt install make`).
Everything else, including Java and Python, is downloaded into `.tools/` and `.venv/` in this
folder; nothing is installed system-wide.

```sh
make setup    # JDK 21, the Iceberg Spark jar and a Python virtualenv
```

Without `make`, the same setup is four commands, run from the repository root:

```sh
curl -sSL https://astral.sh/uv/install.sh | UV_INSTALL_DIR=.tools/uv XDG_BIN_HOME=.tools/uv UV_NO_MODIFY_PATH=1 sh
mkdir -p .tools/jdk21 && curl -sSL https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jdk/hotspot/normal/eclipse | tar -xz -C .tools/jdk21 --strip-components=1
.tools/uv/uv venv .venv --python 3.14 && VIRTUAL_ENV=.venv .tools/uv/uv pip install -e ".[dev]"
mkdir -p .tools/jars && curl -sSL -o .tools/jars/iceberg-spark-runtime-4.1_2.13-1.11.0.jar https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-4.1_2.13/1.11.0/iceberg-spark-runtime-4.1_2.13-1.11.0.jar
```

The JDK download is for Linux x64. On macOS, set `JAVA_HOME` to any JDK 21 instead.

### Running

| Command | What it does | Time |
|---|---|---|
| `make test` | The whole suite on a local Iceberg catalog | 3–6 min |
| `make test-fast` | Only the tests that need no Spark session | seconds |
| `make test ARGS="tests/test_partner_files.py -k parts"` | One file, or one test by name | — |
| `make mutation` | Breaks each guard in the source on purpose; every break must make a test fail | about 20 min |
| `make contract-check` | Cube metric filters may only use values the data contracts allow | seconds |
| `make demo` | Runs the three hard problems end to end and prints what happens | 2–3 min |
| `make check` | The tests, the contract check, and a quick check that every mutation still matches the source | 2–4 min |

Without `make`, run the same things directly:

```sh
.venv/bin/pytest                          # the tests
.venv/bin/python demo/run.py              # the demo
.venv/bin/python tests/mutation/run.py    # mutation testing
.venv/bin/python tests/contract_check.py  # the contract check
```

With only Docker, which needs no local setup at all:

```sh
docker build -t lakehouse .
docker run --rm lakehouse                         # the tests
docker run --rm lakehouse python demo/run.py      # the demo
```

## Test Plan

### The Principle

Every test provokes a **plausible wrong answer, not a crash**. A pipeline that crashes gets fixed
the same day. A pipeline that reports ₹30,000 when the truth is ₹10,000 ends up in a board pack.
So each test names the wrong answer a broken design would give.

- **Engine behaviour is tested against a real Iceberg engine:** MERGE, branches, tags, commit
  conflicts and `fast_forward`. Mocks can't prove those.
- **Mutation testing:** each guard in the source is broken on purpose, one at a time, and a test
  must fail. All 20 mutations are caught (`make mutation`).

### Hard problem 1: partner files

[test_partner_files.py](test_partner_files.py)

| ID | Test | Asserts | Wrong answer if the design were wrong |
|---|---|---|---|
| 1.1 | `test_a_truncated_file_whose_trailer_matches_is_held_for_approval` | Far fewer rows than the same weekday usually has: held until approved | Half a day published, and everyone missing from it quietly dropped |
| 1.2 | `test_an_older_version_arriving_late_never_becomes_current` | Version 2 is current in either arrival order | Stale settlements replace corrected ones |
| 1.3 | `test_a_version_in_parts_publishes_only_when_every_part_has_arrived` | Two of three parts: version 1 stays current, unmixed | A "day" mixing parts of two versions, every part tying to its own trailer |
| 1.4 | `test_a_correction_replaces_the_previous_version_and_history_keeps_both` | The correction is current; "as known at" before it returns the old figures; another delivery is untouched | The correction added rather than swapped in, history lost, or another day withdrawn |
| 1.5 | `test_a_rerun_after_a_crash_does_not_load_the_rows_twice` | A crash between append and record, then a rerun: rows loaded once | Every row of the file counted twice |
| 1.6 | `test_two_workers_publishing_the_same_version_at_once_make_one_current_version` | One current version, rows counted once | Two current versions, and the numbers double |
| 1.7 | `test_a_file_that_does_not_match_its_trailer_is_rejected_and_writes_nothing` | Rejected, nothing loaded | Bad rows published |
| 1.8 | `test_two_workers_receiving_the_same_part_at_once_load_it_once` | Two workers race on one part; its rows load once | The same rows counted twice under one version |
| 1.9 | `test_a_partner_identifier_that_could_change_the_sql_is_refused` | A partner or feed name with characters that could alter SQL is refused at the boundary | A partner name changes the meaning of the loader's SQL |

Planned, not yet written as code: **1.10** a file missing when its arrival window closes holds
every dependent gold table; **1.11** a change-only feed stops at a missing sequence number;
**1.12** a reference update is announced only after its pointer flips.

### Hard problem 2: completeness and correctness at zero tolerance

[test_publish_gate.py](test_publish_gate.py)

| ID | Test | Asserts | Wrong answer if the design were wrong |
|---|---|---|---|
| 2.1 | `test_money_moved_between_customers_is_caught_only_by_the_fingerprint` | Counts, totals and keys all equal; the fingerprint differs; held | ₹5,000 credited to the wrong customer, every check green |
| 2.2 | `test_an_incomplete_input_holds_the_table_and_readers_keep_the_previous_version` | Held, main untouched, branch kept | An incomplete day published as complete |
| 2.3 | `test_a_clean_build_publishes_with_its_version_label` | Published; the label is on the commit | A version nobody can trace to the silver it was built from |
| 2.4 | `test_the_reference_is_silver_as_the_build_read_it_not_silver_now` | Against pinned silver it passes; against today's silver it would break | False breaks every run, or a real break hidden |
| 2.5 | `test_a_date_with_no_rows_now_becomes_empty_instead_of_keeping_old_rows` | The emptied date is empty in the new version | Last run's rows survive and still tie to last run's totals |
| 2.6 | `test_a_cell_only_the_build_has_is_a_break` | A day the source never reported is a failure | A double-loaded day passes |
| 2.7 | `test_publishing_is_refused_when_main_moved_after_the_branch_was_cut` | `fast_forward` refuses; main keeps the other writer's data | A second writer silently overwritten |
| 2.8 | `test_the_spark_fingerprint_matches_the_reference_implementation` | Spark equals the reference, including negative amounts and non-ASCII keys | Every day breaks, or a real break is masked |

Planned, not yet written as code: **2.9** a paise sum that overflows fails the query; **2.10**
readers during a publish see version N or N+1, never part of each; **2.11** an intraday version is
labelled "checked against silver", not "reconciled to source".

### Hard problem 3: a consistent, complete cut across one database

[test_transaction_cut.py](test_transaction_cut.py)

| ID | Test | Asserts | Wrong answer if the design were wrong |
|---|---|---|---|
| 3.1 | `test_a_transaction_enters_the_cut_only_when_every_table_has_all_its_events` | A loan with one of two ledger lines is not in the cut | A disbursed loan with no money moved, tying to silver |
| 3.2 | `test_the_cut_stops_at_the_first_incomplete_transaction_even_if_later_ones_landed` | The cut ends before the incomplete transaction | A later transaction published ahead of an earlier one |
| 3.3 | `test_a_date_is_complete_only_once_the_cut_passes_its_cutoff` | Complete only after a transaction past the cut-off; a heartbeat counts | A short day published because idle and lagging look the same |
| 3.4 | `test_gold_never_sees_a_loan_without_its_ledger_lines` | Nothing advances until the second ledger line lands; then both tables are tagged at one cut; the next cut reads only what is new | Gold reads a torn transaction |
| 3.5 | `test_rerunning_a_cut_after_a_failure_is_safe` | Running the same cut again completes, with the same result | A cut that failed partway can never be rerun |

### Baseline: the ordered merge

[test_cdc_merge.py](test_cdc_merge.py)

| ID | Test | Wrong answer if the guard were missing |
|---|---|---|
| C.1 | `test_an_older_change_arriving_late_never_overwrites_a_newer_one` | A loan's status sent backwards |
| C.2 | `test_a_deleted_row_stays_deleted_when_an_older_update_arrives_after_it` | The final state depends on arrival order |
| C.3 | `test_a_delete_that_arrives_before_its_insert_still_wins` | A deleted loan comes back |
| C.4 | `test_a_truncate_fails_the_batch_instead_of_writing_nulls` | Nulls written over real values |
| C.5 | `test_a_new_incarnation_outranks_higher_positions_from_before_a_restore` | After a restore, new changes are ignored, or old replays win |
| C.6 | `test_an_unchanged_large_column_keeps_its_value` | Real JSON overwritten by Debezium's placeholder |

### Planned: serving consistency (designed, not written as code)

| ID | Case | Expected |
|---|---|---|
| S.1 | The Aurora copy swaps in a new version | Readers see the whole old version or the whole new one |
| S.2 | The Read API joins two tables at different versions | It pins both versions and returns them; it never mixes silently |
| S.3 | Every response | Carries a version and its freshness; fast-path answers carry `verified: false` |
| S.4 | A copy that has fallen behind gold | The version label shows the gap, and an alert fires past a threshold |
| S.5 | ClickHouse is loaded | Only from a version that passed the gate |
| S.6 | Money screens | Never served by the Read API |

### Planned: the one-time migration (designed, not written as code)

| ID | Case | Expected |
|---|---|---|
| M.1 | A change committed while the export is running | It appears in silver exactly once |
| M.2 | A row from the export, then a later change to it from the stream | The later change applies; a replayed older one doesn't |
| M.3 | A legacy partner file with no sequence number | Ordered by posting date, and labelled as more weakly checked |

### What is not tested, and why

| Not tested | Why |
|---|---|
| **Merge throughput at 10k events/s** | Needs a cluster and a load generator. Delete files piling up from merges, plus compaction, is where this design most plausibly breaks for a boring reason |
| Glue itself | Tests use a filesystem catalog. Table behaviour is identical; commit coordination isn't |
| Real Debezium and Postgres | The transaction cut assumes Debezium's documented END records and event counts; the Postgres side of the fingerprint is stated in SQL and matched by a reference implementation, not run |
| ClickHouse, Aurora and Cube | None of them is stood up |
| The tokenisation vault and the Flink fast path | Designed, not built |

## Files

| File | Covers | Test IDs |
|---|---|---|
| [test_partner_files.py](test_partner_files.py) | Hard problem 1: which version of a partner delivery is current, and whether it is whole | 1.x |
| [test_publish_gate.py](test_publish_gate.py) | Hard problem 2: gold publishes only when complete and tied to the paise | 2.x |
| [test_transaction_cut.py](test_transaction_cut.py) | Hard problem 3: silver advances only to a consistent, complete cut of each database | 3.x |
| [test_cdc_merge.py](test_cdc_merge.py) | Baseline: the ordered merge of database changes | C.x |
| [mutation/run.py](mutation/run.py) | Mutation testing: one entry per guard | — |
| [contract_check.py](contract_check.py) | Cube model against the data contracts | — |
| [fixtures/iceberg_session.py](fixtures/iceberg_session.py) | The shared Spark session and a fresh namespace per test | — |

The fixtures module is loaded as a pytest plugin from `pyproject.toml`, in place of a
`conftest.py`, so it can have a name that says what it holds.

### Conventions

- A test's name states the behaviour it proves, for example
  `test_an_older_version_arriving_late_never_becomes_current`.
- Each test arranges, acts, then asserts, and asserts the specific wrong answer a broken design
  would give.
- Tests that need Spark are marked `spark`. Every test gets its own namespace, so tests never
  share tables.
