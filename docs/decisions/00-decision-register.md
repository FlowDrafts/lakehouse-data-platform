# Decision Log

A decision gets a full Architecture Decision Record (ADR) when it is hard to reverse, had credible
alternatives, or carries a guarantee the design depends on. Every other decision is recorded below
as a lightweight decision. The design is described in the
[technical design document](../architecture/lakehouse-design.md).

## Architecture Decision Records

| ID | Decision | Status | Primary cost |
|---|---|---|---|
| [ADR-01](01-catalog-and-consistency.md) | Glue as the catalog; consistency enforced through published versions | Accepted | Readers must resolve a published version, never "latest" |
| [ADR-02](02-personal-data-tokenisation.md) | Tokenise personal data before anything stores it, using vault-issued random tokens | Accepted | The vault sits on the critical ingestion path |
| [ADR-03](03-database-changes-into-the-lake.md) | The connector appends to bronze; Spark merges into silver in order | Accepted | Two hops, and merge code we own |
| [ADR-04](04-partner-and-ops-files.md) | Partner files: register, append, then flip a current-version pointer | Accepted | Readers go through the pointer; every version is stored |
| [ADR-05](05-the-publish-gate.md) | Build gold on a temporary branch, check it, then publish or hold | Accepted | A late input holds the tables that depend on it |
| [ADR-06](06-application-reads.md) | Application reads: money from the owning service, derived data from Aurora | Accepted | Two read paths in every app |
| [ADR-07](07-bi-serving.md) | BI on a ClickHouse copy of published gold, with Cube defining each metric | Accepted | A second copy, with no history |
| [ADR-08](08-the-fast-path.md) | Flink fast path on complete facts only, always labelled unverified | Accepted | Unverified signals reach apps, by design |
| [ADR-09](09-one-time-migration.md) | One-time migration: export joined to the change stream at the slot's position | Accepted | History for current-state tables starts on migration day |
| [ADR-10](10-transaction-cut.md) | Silver advances to a consistent transaction cut, from Debezium's transaction metadata | Accepted | Silver is as fresh as the slowest partition of its source |

## Lightweight Decisions

| Area | Decision | Alternatives | Consequence | Revisit when |
|---|---|---|---|---|
| Table format | Apache Iceberg | Delta Lake, Hudi | We own compaction, snapshot expiry and delete-file cleanup | A required engine lacks Iceberg support |
| Layers | Bronze, silver and gold for every source | Skipping layers for small tables | Some storage and compute spent on tiny tables | — |
| Batch processing | Spark on EKS for silver merges, gold builds and backfill | Flink for everything; Glue ETL | Minutes of latency, not seconds | Merges can't keep up ([ADR-03](03-database-changes-into-the-lake.md)) |
| Orchestration | Airflow, with the gate as a blocking task | Dagster | Task-based, not asset-based; we track freshness ourselves | Asset-level lineage becomes the main way the platform is operated |
| Event bus | Amazon MSK, provisioned: a broker in each of 3 availability zones, in private subnets | MSK Serverless; self-run Kafka | We size the brokers | Partitions or retention outgrow provisioned limits |
| Kafka topic sizing | Event topics partitioned by `customer_id`; ~540 partitions in total, sized for consumer parallelism. Change-topic settings are in [ADR-03](03-database-changes-into-the-lake.md) | Sizing on throughput, which needs only 2 | About 5 TB retained | Consumer parallelism needs change |
| Kafka Connect | Self-run on EKS with the Strimzi operator | MSK Connect | We operate it | Operating it costs more than the control is worth |
| Deployment | Terraform for AWS; Helm and Argo CD (GitOps) on EKS; dev, staging and prod accounts ([deploy](../../deploy/README.md)) | Hand-applied manifests; CloudFormation | Argo CD and the operators are more to run | — |
| Region | AWS `ap-south-1` only; recovery in `ap-south-2` (Hyderabad) is designed | Regions outside India | Regional recovery isn't built or rehearsed | Build and rehearse before go-live |
| Landing zone | S3, encrypted; raw files kept 14 days | 30 days | Assumes partners raise disputes within 14 days | A contract allows longer disputes |
| Money | Signed `BIGINT` paise; rates in integer basis points; Spark's ANSI mode fails on overflow | `DECIMAL`, floating point | Every unit conversion is explicit | — |
| Partitioning | Bronze by ingest hour; silver current-state bucketed on the merge key; file facts by business date and partner; gold by day | Business line × event type × hour (>200,000 files a day per table) | Bucket counts are fixed per table layout | — |
| Business day | Asia/Kolkata, assigned at the source; each partner's cut-off is declared in its contract | Deriving it from UTC timestamps | Every contract must state its cut-off | — |
| Audit, ad hoc and data science reads | Spark on Iceberg through Glue, with time travel and month-end tags | Trino | Slower than ClickHouse | — |
| Lineage and quality results | OpenLineage from Spark, the connector and Flink, plus checkpoint results, into OpenMetadata | Lineage from Spark only | Three emitters to keep wired | — |
| Metrics and alerting | VictoriaMetrics (Prometheus-compatible, with long-term storage), Grafana, Alertmanager | Prometheus with local storage | Less widely used than Prometheus | — |
| Data contracts | One per source and gold table, in the Open Data Contract Standard (ODCS) v3.2 ([samples](../../contracts/README.md)) | A home-grown YAML format | Platform-specific settings sit under `customProperties` | — |
| Metric meaning | Cube's single metric definitions, a contract per table, and OpenMetadata's glossary and lineage | A query-time validator that refuses unsafe queries; it only protects people who route through it | Nothing blocks a wrong aggregation run directly on ClickHouse or Spark | Wrong aggregations become a recurring incident |
| Testing | A real Iceberg engine, plus mutation testing of every guard | Mocks only | A slower suite that needs a JVM | — |

## Open Decisions

| Area | Options | Status | Needed by |
|---|---|---|---|
| Schema registry | Confluent Schema Registry on EKS, which works with today's converters; or AWS Glue Schema Registry, which is AWS-native but needs different converters | Proposed | Before the first connector is deployed |
