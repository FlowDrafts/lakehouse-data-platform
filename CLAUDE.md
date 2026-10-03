# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What This Is

A lakehouse design for lending, insurance and recharge on Apache Iceberg, with reference code for
three hard problems. Read [README.md](README.md) first, then the
[design document](docs/architecture/lakehouse-design.md).

- `src/lakehouse/`: `ingestion/partner_files.py`, `ingestion/transaction_cut.py`,
  `ingestion/cdc_merge.py`, `publishing/publish_gate.py`; `pipeline.py` holds plumbing stubs.
- `tests/`: the test plan (`tests/README.md`), tests on a real Iceberg engine, mutation testing
  (`tests/mutation/run.py`), and the contract check.
- `docs/`: design, decisions (ADRs), runbooks, and the spec in `docs/spec/` (constitution,
  spec, plan, tasks). Start any work there.

## Commands

```sh
make setup            # JDK 21, the Iceberg jar and the virtualenv, all local
make test             # the whole suite on a real Iceberg engine (3–6 minutes)
make test-fast        # only the tests that need no Spark session
make mutation         # break each guard on purpose; every break must fail a test (~20 min)
make contract-check   # Cube metric filters must use values the data contracts allow
make demo             # the three hard problems end to end
```

Lint with `ruff check .` and `ruff format --check .` (ruff 0.14.2, as in CI).

## Conventions

- **Money** is a signed integer number of paise; rates are integer basis points. Never float or
  decimal.
- **Tests** are named for the behaviour they prove, run on the real engine (not mocks), and
  assert the specific wrong answer a broken design would give.
- **Every guard** in the hard-problem code has an entry in `tests/mutation/run.py`, and that
  mutation must make a test fail.
- **Partner-supplied values** never reach SQL unchecked: validate them with `require_safe`.
- **A new decision** gets an ADR in `docs/decisions/`; a new test gets an ID in `tests/README.md`;
  a new failure mode gets a runbook row.
- **No company names, no brief text, no secrets** in the repository.

## Workflow

1. Start from `docs/spec/`: keep the constitution, take a task from `tasks.md`, and plan before
   changing anything non-trivial. Update the spec (task, story, test IDs) in the same change.
2. Before committing: `make test`, ruff, and `.venv/bin/python tests/mutation/run.py --check`.
3. Never push, force-push, or rewrite history without the author's explicit approval.
