# Technical Plan

How the [specification](spec.md) is built. Read this before planning a change: it records the
stack, where each story lives, the interfaces between modules, and the engine behaviour that
isn't obvious.

## Stack

| Concern | Choice | Version |
|---|---|---|
| Language | Python | 3.12+ (3.14 locally) |
| Engine | Apache Spark | 4.1.3, pinned: no Iceberg runtime exists for 4.2 yet |
| Table format | Apache Iceberg | 1.11 (`iceberg-spark-runtime-4.1_2.13`) |
| Java | JDK | 21 (17 in the Docker image) |
| Tests | pytest, on a local filesystem Iceberg catalog | — |
| Lint | ruff | 0.14.2, pinned to match CI |

## Where Each Story Lives

| Story | Code | Tests | Tables (DDL) |
|---|---|---|---|
| US-1 Partner files | `src/lakehouse/ingestion/partner_files.py` | `tests/test_partner_files.py` | `control.file_register`, `control.file_pointer`, `silver.partner_settlement_versions` |
| US-2 Publish gate | `src/lakehouse/publishing/publish_gate.py` | `tests/test_publish_gate.py` | `gold.fact_transaction` |
| US-3 Transaction cut | `src/lakehouse/ingestion/transaction_cut.py` | `tests/test_transaction_cut.py` | `bronze.lending_transactions`, bronze change tables |
| US-4 Ordered merge | `src/lakehouse/ingestion/cdc_merge.py` | `tests/test_cdc_merge.py` | `silver.loan` |
| US-5, US-6, US-7 | Stubs in `src/lakehouse/pipeline.py` | Planned (S.x, M.x) | — |

The table definitions are in `tables/`, the contracts in `contracts/`, and the deployables in
`deploy/`.

## Interfaces Between Modules

- **`InputStatus`** (`models.py`): each source reports whether it is complete by its own signal.
  `PartnerFileLoader.input_status(delivery)` and `transaction_cut.input_status(source, cut,
  cutoff)` produce it; `publish_or_hold(..., inputs=...)` consumes it.
- **`MergeSpec`** (`cdc_merge.py`): how one silver table is merged. `CdcTable` pairs it with a
  bronze table and the source table's name, for the cut.
- **Version labels** are Iceberg snapshot properties (`lakehouse.*`), written with the
  per-commit `snapshot-property.` write option, never through session-wide Spark settings.
- **Cuts** are Iceberg tags named `cut_<source>_<position>`; gold reads every input with
  `VERSION AS OF '<tag>'`.

## Engine Behaviour to Respect

Each of these was found by running against the real engine; a plan that ignores one will fail.

| Behaviour | Consequence |
|---|---|
| Spark 4.1 can't plan a MERGE whose source view still reads another Iceberg table | Materialise the source first (`localCheckpoint()`), as `merge_changes` does |
| Iceberg's MERGE doesn't support Spark's SQL parameter markers | Validate identifiers with `require_safe` before building SQL |
| Iceberg keeps only 16 characters of string column statistics by default | Tables replaced by a string key need `write.metadata.metrics.column.<col> = 'full'` |
| The `snapshot-id` read option is no longer supported | Use `VERSION AS OF <id or tag>` |
| Concurrent commits to the same files conflict | Retry on conflict (`PartnerFileLoader._retry`); decide inside one MERGE (compare-and-set), never check-then-write |
| `CREATE TAG` fails if the tag exists | Use `CREATE TAG IF NOT EXISTS`, so reruns are safe |
| Spark compares timestamps in the session time zone (UTC) | Pass timezone-aware datetimes; never naive ones |

## Testing Approach

- **Fixtures** live in `tests/fixtures/iceberg_session.py`, loaded as a pytest plugin. There is
  one Spark session per run, and each test gets a fresh namespace.
- **Each test** arranges, acts, then asserts the specific wrong answer a broken design gives. Its
  name states the behaviour.
- **Each guard** gets a mutation entry: a find-string in the source, its replacement, and the
  test that must fail.
- **CI** runs lint, tests on Python 3.12 and 3.14, mutation testing, Docker, the contract and
  manifest checks, the link check, and secret and dependency scans.
