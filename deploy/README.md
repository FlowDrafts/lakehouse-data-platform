# Deployment

How the platform is deployed, and how to set up an environment. The files here are samples, one
of each kind of deployable, to show what a deployment looks like.

**Scope.** This describes the intended process. Terraform modules, Helm values and
per-environment settings are out of scope for this design. The release workflow is a sample: it
stays skipped until an AWS role is configured.

## Contents

| File | What it deploys | Decision |
|---|---|---|
| [kafka-connect/debezium-lending.yaml](kafka-connect/debezium-lending.yaml) | The Debezium source for the lending database, as a Strimzi `KafkaConnector`, with transaction metadata for the transaction cut | [ADR-02](../docs/decisions/02-personal-data-tokenisation.md), [ADR-03](../docs/decisions/03-database-changes-into-the-lake.md), [ADR-10](../docs/decisions/10-transaction-cut.md) |
| [kafka-connect/iceberg-sink-bronze.yaml](kafka-connect/iceberg-sink-bronze.yaml) | The Iceberg sink connectors that append changes and transaction records to bronze, with their Kafka offsets | [ADR-03](../docs/decisions/03-database-changes-into-the-lake.md), [ADR-10](../docs/decisions/10-transaction-cut.md) |
| [airflow/dags/gold_publish.py](airflow/dags/gold_publish.py) | A gold table's build, check, publish and copy loads. Each step runs the job image, which calls [publish_gate.py](../src/lakehouse/publishing/publish_gate.py) | [ADR-05](../docs/decisions/05-the-publish-gate.md) |
| [cube/model/transactions.yml](cube/model/transactions.yml) | One metric definition, refreshed per published version | [ADR-07](../docs/decisions/07-bi-serving.md) |

## Environments

There are three AWS accounts, dev, staging and prod, all in `ap-south-1`. Each runs the same
stack from the same code; only sizes and secrets differ.

| Layer | What runs | Deployed with |
|---|---|---|
| AWS infrastructure | VPC, S3, KMS, Glue, Lake Formation, MSK, Aurora, EKS | Terraform |
| Operators on EKS | Strimzi, Spark Operator, Flink Kubernetes Operator, ClickHouse operator | Helm |
| Platform services | Kafka Connect, Airflow, Cube, ClickHouse, OpenMetadata, VictoriaMetrics, Grafana | Helm, synced by Argo CD |
| Pipelines | Connectors, Spark and Flink jobs, DAGs, the Cube model, contracts | This repository. Manifests are synced by Argo CD, and DAGs by Airflow's git-sync |

- **Secrets** stay in AWS Secrets Manager, and reach pods through the External Secrets Operator.
- **AWS access** is through IAM roles for service accounts, never static keys.
- **CI reaches AWS through GitHub OIDC.** It swaps a short-lived GitHub token for temporary
  credentials from an IAM role that trusts only this repository's `main` branch. No AWS key is
  stored, not even in Secrets Manager: reading a secret would itself need a key first.
- **A new environment** is set up layer by layer, in the order of the table above.

## How a Change Is Deployed

1. **Pull request.** [CI](../.github/workflows/ci.yml) runs the tests and mutation testing. It
   validates the contracts against the standard, the manifests, the DAGs and the table
   definitions, and checks doc links.
2. **Merge.** Once CI passes on `main`, [the release workflow](../.github/workflows/release.yml)
   builds the job image and pushes it to ECR, tagged with the commit.
3. **Dev and staging.** Argo CD syncs the change automatically.
4. **Prod.** The change is promoted by a reviewed change that pins the new image tag.
5. **Rollback.** Revert the commit, and Argo CD syncs back. Rolling back data is a separate
   procedure ([runbooks](../docs/runbooks/00-runbook-index.md)).

## Local Setup

For development and tests only. It uses a local Iceberg catalog, not AWS.

```sh
make setup   # uv, JDK 21, the Iceberg jar and the virtualenv, all under .tools/
make test    # the test suite, against a real Iceberg engine
```

With only Docker: `docker build -t lakehouse . && docker run --rm lakehouse`.
