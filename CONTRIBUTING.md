# Contributing

Thanks for helping. This repository is a design plus reference code, so a change is judged on
two things: does the guarantee still hold, and is the reasoning written down.

## Setup

You need Linux, macOS or WSL, with `curl` and `make`. Everything else downloads into the
repository folder.

```sh
make setup    # JDK 21, the Iceberg jar and the virtualenv
make test     # confirm everything passes before you start
```

Without `make`, see the plain commands in [tests/README.md](tests/README.md).

## Workflow

1. **Branch** from `main`.
2. **Plan anything non-trivial first.** Write what you'll change, why, and how you'll verify it.
   If you work with an AI assistant, save the approved plan in [docs/spec/](docs/spec/README.md).
3. **Make the change, with its tests and docs** (see below).
4. **Open a pull request.** [Code owners](.github/CODEOWNERS) review changes to contracts, deploy
   samples, table definitions and decisions.

## Standards

- **Python:** ruff (0.14.2, as in CI) for lint and formatting; type hints on public functions;
  short docstrings that state the guarantee and why it holds.
- **Money** is a signed integer number of paise. Never float or decimal.
- **Tests** are named for the behaviour they prove, run on a real Iceberg engine, and assert the
  specific wrong answer a broken design would give.
- **Guards:** every guard in the hard-problem code has an entry in
  [tests/mutation/run.py](tests/mutation/run.py), and breaking it must make a test fail.
- **Partner-supplied values** are validated before they reach SQL.

## Before Opening a Pull Request

```sh
make check                                     # tests, contract check, mutation find-strings
ruff check . && ruff format --check .
.venv/bin/python tests/mutation/run.py         # if you changed a guard (about 20 minutes)
```

CI runs all of this, plus secret and dependency-vulnerability scans.

## Keep the Docs in Step

| You changed | Also update |
|---|---|
| An architecture decision | An ADR in [docs/decisions/](docs/decisions/00-decision-register.md), and the register |
| A guarantee or a test | The test plan in [tests/README.md](tests/README.md), with an ID |
| A failure mode or an alert | A row in the [runbooks](docs/runbooks/00-runbook-index.md) |
| The architecture diagram | `docs/architecture/lakehouse_architecture.mmd`, then `make diagram` |

## Commits

- Say what changed and why, in the present tense: "Hold a truncated file for approval".
- Keep one logical change per commit.
- Never commit secrets, tokens, real customer data, or company-confidential text.
