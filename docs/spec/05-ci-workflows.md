# Plan: `.github` aligned with the design, with industry-standard GitHub Actions, kept simple

## Context

The user asked which GitHub Actions `.github` should include. Today it has one workflow,
`ci.yml`, with five jobs: tests, breakages (mutation testing), contracts, lint (ruff) and docker.
Three gaps:
- **The contracts job is stale.** It runs `tests/contract_lint.py`, which reads the old contract
  format and now passes without checking anything.
- **The new folders are unchecked.** Nothing validates `contracts/` (ODCS), `deploy/` (Strimzi
  manifest, Airflow DAG, Cube model) or `tables/` (DDL), or links in the docs.
- **No release or dependency hygiene.** There's no image build and push, which
  `deploy/README.md` describes, and no Dependabot.

There's also a live break: ruff lints `deploy/`, and the sample DAG's naive
`datetime(2026, 10, 1)` breaks rule `DTZ001`.

The user's standing direction: industry standard, simple, sample-level, and no test runs for now
(the workflows are written, not executed).

## Target layout

```
.github/
├── workflows/
│   ├── ci.yml          pull request and push to main: checks only, no AWS access
│   └── release.yml     push to main: build the image, push it to ECR (sample, skipped until configured)
├── dependabot.yml      weekly updates for pip, GitHub Actions and Docker
└── CODEOWNERS          contracts/, deploy/ and tables/ need the platform owner's review
```

## `ci.yml`: keep the existing jobs, fix one, add three

| Job | Status | What it does |
|---|---|---|
| `lint` | keep | `ruff check` / `ruff format --check`, plus the breakage find-string check |
| `tests` | keep | pytest against a real Iceberg engine (Python 3.12, 3.14) |
| `breakages` | keep | mutation testing: every guard deleted in turn must fail a test |
| `docker` | keep | the suite runs inside the image |
| `contracts` | **replace** | Validate every `contracts/**/*.odcs.yaml` against the official ODCS v3.2.0 JSON schema with `check-jsonschema`, replacing the stale `contract_lint.py` call |
| `deploy` | **new** | (1) A DAG integrity check: load `deploy/airflow/dags` with Airflow's `DagBag` and fail on any import error. (2) `kubeconform` on `deploy/kafka-connect/` with the CRD catalog for Strimzi. (3) `yamllint` on `deploy/` and `contracts/` |
| `tables` | **new** | `sqlfluff parse` per dialect (`sparksql` for `iceberg/`, `clickhouse`, `postgres` for `aurora/`). Syntax only, not style |
| `docs` | **new** | `lychee --offline` over all Markdown, so a broken internal link fails the build |

- Bump action versions (`checkout`, `setup-python`, `setup-java`) to current majors.
- Keep `permissions: contents: read` and the existing `concurrency` block.

## `release.yml` (sample)

- Triggered by a push to `main`.
- `permissions: id-token: write, contents: read`: GitHub OIDC, so there are no stored AWS keys.
- The job runs only `if: vars.AWS_ROLE_ARN != ''`, so it skips cleanly until AWS is set up.
- Steps:
  1. `aws-actions/configure-aws-credentials`, assuming the role in `ap-south-1`;
  2. `aws-actions/amazon-ecr-login`;
  3. `docker/build-push-action`, pushing `platform-jobs:${{ github.sha }}`.
- Dev and staging pick up the new tag through Argo CD. Prod is a reviewed change that pins the
  tag, matching `deploy/README.md`.

## `dependabot.yml` and `CODEOWNERS`

- **Dependabot:** `pip`, `github-actions` and `docker` ecosystems, weekly, grouped to limit noise.
- **CODEOWNERS:** `/contracts/`, `/deploy/`, `/tables/` and `/docs/decisions/` owned by
  `@<platform-owner>`, a placeholder like `<your name>` in the docs. This backs the rule that a
  contract change is reviewed like code.

## Small related edits

- `deploy/airflow/dags/gold_publish.py`: make `start_date` timezone-aware, to satisfy the existing
  `DTZ001` rule.
- `deploy/README.md`: update the scope line ("CI currently runs only the tests") to match the new
  jobs, and name `release.yml` in "How a Change Is Deployed".

## Not changed

- `tests/contract_lint.py` stays in place, no longer called by CI. It is rewritten or removed in
  the code rewrite.
- No workflow is run as part of this change.

## Verification (static only; no tests run)

- `actionlint` (downloaded to the scratchpad) on both workflows: zero findings.
- `check-jsonschema` on `dependabot.yml` against its official schema.
- `ruff check deploy/` passes after the `start_date` fix.
- A grep confirms no workflow still calls `contract_lint.py`.
