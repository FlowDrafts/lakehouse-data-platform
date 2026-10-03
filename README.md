<h1 align="center">Lakehouse Data Platform</h1>

<p align="center">
  One trusted lakehouse for lending, insurance and recharge.<br/>
  <b>No gold table becomes readable until it is proven complete and correct, to the paise.</b>
</p>

## Architecture

![Lakehouse architecture: sources, ingestion, the Iceberg lakehouse with its publish gate, serving, and consumers](docs/architecture/lakehouse_architecture.png)

Data flows top to bottom through five layers. Database changes arrive through Debezium and Kafka;
files and API responses land in S3. Everything is appended to bronze, merged in order into silver,
and built into gold on a branch that a **publish gate** checks before anyone can read it. Money a
customer sees is read live from its service, and an optional Flink lane serves labelled,
unverified signals in seconds.

**[Detailed architecture (hand-drawn) →](docs/architecture/lakehouse_architecture_detailed.png)**
Every component and connection, with its [editable draw.io source](docs/architecture/lakehouse_architecture.drawio).
The full walkthrough is in the [technical design document](docs/architecture/lakehouse-design.md).

## What It Guarantees

- **Correct.** Every published gold table ties to its source on row count, signed paise, distinct
  keys and a content fingerprint, with zero tolerance.
- **Complete.** Each input proves itself complete by its own signal: a partner delivery by its
  current version, a database by its transaction cut.
- **Current, and honest about it.** Every answer states its version, how fresh it is, and whether
  it was verified.

## The Hard Problems

Chosen from how the sources actually misbehave ([design §10](docs/architecture/lakehouse-design.md)).

| Problem | Code | Tests |
|---|---|---|
| **Partner files:** which version of a delivery is the truth, and is it whole? | [partner_files.py](src/lakehouse/ingestion/partner_files.py) | [test_partner_files.py](tests/test_partner_files.py) |
| **Completeness and correctness at zero tolerance** | [publish_gate.py](src/lakehouse/publishing/publish_gate.py) | [test_publish_gate.py](tests/test_publish_gate.py) |
| **A consistent cut across one database** (the hidden one) | [transaction_cut.py](src/lakehouse/ingestion/transaction_cut.py) | [test_transaction_cut.py](tests/test_transaction_cut.py) |
| Baseline: the ordered merge of database changes | [cdc_merge.py](src/lakehouse/ingestion/cdc_merge.py) | [test_cdc_merge.py](tests/test_cdc_merge.py) |

The plumbing around them (API pulls, Ops sheets, loading the serving copies, month-end tags) is
stubbed in [pipeline.py](src/lakehouse/pipeline.py), as the brief allows. Each stub states the
guarantee the real job must keep.

## Tech Stack

| Layer | Technology |
|---|---|
| Ingestion | ![Debezium](https://img.shields.io/badge/Debezium-48A23F?style=flat-square) ![Apache Kafka](https://img.shields.io/badge/Apache_Kafka-231F20?style=flat-square&logo=apachekafka&logoColor=white) ![Kafka Connect](https://img.shields.io/badge/Iceberg_sink_connector-2C6BB5?style=flat-square) |
| Storage and catalog | ![Apache Iceberg](https://img.shields.io/badge/Apache_Iceberg-2C6BB5?style=flat-square) ![Amazon S3](https://img.shields.io/badge/Amazon_S3-FF9900?style=flat-square) ![AWS Glue](https://img.shields.io/badge/AWS_Glue_catalog-FF9900?style=flat-square) |
| Processing | ![Apache Spark](https://img.shields.io/badge/Apache_Spark-E25A1C?style=flat-square&logo=apachespark&logoColor=white) ![Apache Flink](https://img.shields.io/badge/Apache_Flink-E6526F?style=flat-square&logo=apacheflink&logoColor=white) |
| Orchestration and quality | ![Apache Airflow](https://img.shields.io/badge/Apache_Airflow-017CEE?style=flat-square&logo=apacheairflow&logoColor=white) ![Great Expectations](https://img.shields.io/badge/Great_Expectations_%2F_Soda-FF6310?style=flat-square) |
| Serving | ![ClickHouse](https://img.shields.io/badge/ClickHouse-FFCC01?style=flat-square&logo=clickhouse&logoColor=black) ![Cube](https://img.shields.io/badge/Cube-7A77FF?style=flat-square) ![Aurora PostgreSQL](https://img.shields.io/badge/Aurora_PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white) |
| Governance and monitoring | ![OpenMetadata](https://img.shields.io/badge/OpenMetadata-7147E8?style=flat-square) ![VictoriaMetrics](https://img.shields.io/badge/VictoriaMetrics-621773?style=flat-square&logo=victoriametrics&logoColor=white) ![Grafana](https://img.shields.io/badge/Grafana-F46800?style=flat-square&logo=grafana&logoColor=white) |
| Platform and delivery | ![Kubernetes](https://img.shields.io/badge/Amazon_EKS-326CE5?style=flat-square&logo=kubernetes&logoColor=white) ![Terraform](https://img.shields.io/badge/Terraform-844FBA?style=flat-square&logo=terraform&logoColor=white) ![Helm](https://img.shields.io/badge/Helm-0F1689?style=flat-square&logo=helm&logoColor=white) ![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=flat-square&logo=githubactions&logoColor=white) |

Why each was chosen, and what it costs, is in the [decision log](docs/decisions/00-decision-register.md).

## Repository Guide

| Area | Where | What's there |
|---|---|---|
| Design | [docs/architecture/](docs/architecture/lakehouse-design.md) | Technical design document, the overview diagram, and the detailed hand-drawn diagram |
| Decisions | [docs/decisions/](docs/decisions/00-decision-register.md) | Decision log and ten architecture decision records |
| Operations | [docs/runbooks/](docs/runbooks/00-runbook-index.md) | On-call runbooks, mapped to alerts |
| Specifications | [docs/spec/](docs/spec/README.md) | The approved plans that drove the AI-assisted development |
| Source | [src/lakehouse/](src/lakehouse/) | The hard problems, the ordered merge, and the plumbing stubs |
| Tests | [tests/](tests/README.md) | Test plan, tests on a real Iceberg engine, mutation testing |
| Demo | [demo/](demo/run.py) | The three problems end to end, printed step by step |
| Data contracts | [contracts/](contracts/README.md) | Sample contracts in the Open Data Contract Standard |
| Table definitions | [tables/](tables/README.md) | Sample DDL for Iceberg, ClickHouse and Aurora |
| Deployment | [deploy/](deploy/README.md) | Sample Kafka Connect, Airflow and Cube deployables, and how releases work |
| CI/CD | [.github/](.github/workflows/ci.yml) | CI (lint, tests, mutation testing, secret and dependency scans), release, Dependabot and code owners |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) · [CLAUDE.md](CLAUDE.md) | How to contribute, and the guide for AI-assisted work in this repo |

## Quick Start

You need Linux, macOS or WSL, with `curl` and `make`. Java, Python and Spark are downloaded into
the repository folder; nothing is installed system-wide.

```sh
make setup      # JDK 21, the Iceberg jar and a Python virtualenv
make test       # 31 tests on a real Iceberg engine, 3–6 minutes
make demo       # the three problems end to end, 2–3 minutes
make mutation   # break each of 20 guards on purpose; every break must fail a test
```

No `make`, or only Docker? The [tests README](tests/README.md) has the same steps as plain commands.

## Project Status

- **Built and tested:** the three hard problems and the ordered merge. 31 tests pass on a real
  Iceberg engine, and all 20 deliberately broken guards are caught.
- **Stubbed:** the plumbing around them, in [pipeline.py](src/lakehouse/pipeline.py).
- **Designed, not built:** the serving copies, the Flink fast path, the tokenisation vault, and
  disaster recovery in a second region. Tests use a local filesystem catalog in place of Glue.
- **Known limits:** restatement of closed periods, matching across sources, and source purges are
  named but not solved. See [design §14](docs/architecture/lakehouse-design.md).
