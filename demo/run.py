"""Run the three hard problems end to end on a local Iceberg catalog.

    .venv/bin/python demo/run.py      (or: make demo; in Docker: python demo/run.py)

Each scenario prints what happened. Spark, Iceberg, MERGE, branches and tags are real; Kafka,
Debezium and the partner's files are simulated as small in-memory batches.
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WAREHOUSE = REPO / ".tools" / "demo-warehouse"
os.environ.setdefault("JAVA_HOME", str(REPO / ".tools" / "jdk21"))
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)

from pyspark.sql import SparkSession  # noqa: E402

from lakehouse.ingestion.cdc_merge import MergeSpec  # noqa: E402
from lakehouse.ingestion.partner_files import (  # noqa: E402
    Delivery,
    FeedContract,
    FilePart,
    PartnerFileLoader,
    PartnerFileTables,
)
from lakehouse.ingestion.transaction_cut import CdcTable, advance_to_cut, read_at_cut  # noqa: E402
from lakehouse.models import InputStatus  # noqa: E402
from lakehouse.publishing.publish_gate import publish_or_hold, write_candidate  # noqa: E402


def start_spark() -> SparkSession:
    shutil.rmtree(WAREHOUSE, ignore_errors=True)
    default_jar = REPO / ".tools/jars/iceberg-spark-runtime-4.1_2.13-1.11.0.jar"
    jar = os.environ.get("ICEBERG_SPARK_JAR", str(default_jar))  # the Docker image sets this
    spark = (
        SparkSession.builder.master("local[2]")
        .appName("lakehouse-demo")
        .config("spark.jars", str(jar))
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config("spark.sql.catalog.lake", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.lake.type", "hadoop")
        .config("spark.sql.catalog.lake.warehouse", str(WAREHOUSE))
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.ui.enabled", "false")
        .config("spark.ui.showConsoleProgress", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    spark.sql("CREATE NAMESPACE IF NOT EXISTS lake.demo")
    return spark


def say(text: str) -> None:
    print(f"   {text}")


def partner_files(spark: SparkSession) -> None:
    print("\n1. Partner files: a correction sent in three parts, and an old version sent again")
    tables = PartnerFileTables(
        "lake.demo.file_register", "lake.demo.settlements", "lake.demo.file_pointer"
    )
    spark.sql(f"""CREATE TABLE {tables.register} (file_id STRING, file_hash STRING, partner STRING,
        feed STRING, posting_date DATE, sequence_number BIGINT, part_number INT, part_count INT,
        row_count BIGINT, amount_paise BIGINT, state STRING, reason STRING,
        registered_at TIMESTAMP) USING iceberg""")
    spark.sql(f"""CREATE TABLE {tables.rows} (partner STRING, feed STRING, sequence_number BIGINT,
        file_id STRING, settlement_id STRING, amount_paise BIGINT, posting_date DATE)
        USING iceberg TBLPROPERTIES ('write.metadata.metrics.column.file_id' = 'full')""")
    spark.sql(f"""CREATE TABLE {tables.pointer} (partner STRING, feed STRING, posting_date DATE,
        sequence_number BIGINT, valid_from TIMESTAMP, valid_to TIMESTAMP, approved_by STRING)
        USING iceberg""")
    loader = PartnerFileLoader(spark, tables, FeedContract(key_columns=("settlement_id",)))
    delivery = Delivery("acme", "settlement", date(2026, 3, 2))

    def send(version: int, part: int, of: int, amounts: list[int]):
        rows = [(f"S{part}-{i}", a, delivery.posting_date) for i, a in enumerate(amounts)]
        frame = spark.createDataFrame(
            rows, "settlement_id STRING, amount_paise BIGINT, posting_date DATE"
        )
        file_id = f"v{version}-p{part}"
        part_info = FilePart(
            file_id, f"sha-{file_id}", delivery, version, part, of, len(amounts), sum(amounts)
        )
        say(f"version {version}, part {part} of {of}: {loader.receive(part_info, frame)}")

    def current() -> str:
        row = (
            loader.current_rows()
            .selectExpr("count(1) n", "coalesce(sum(amount_paise), 0) t")
            .first()
        )
        return f"{row.n} rows, {row.t} paise"

    send(1, 1, 1, [100, 200])
    say(f"publish version 1: {loader.publish(delivery, 1)} -> current is {current()}")
    send(2, 1, 3, [150])
    send(2, 2, 3, [250])
    say(f"publish version 2: {loader.publish(delivery, 2)} -> current is still {current()}")
    send(2, 3, 3, [50])
    say(f"publish version 2: {loader.publish(delivery, 2)} -> current is {current()}")
    send(1, 1, 1, [100, 200])
    say(f"publish version 1 again: {loader.publish(delivery, 1)} -> current is {current()}")


def transaction_cut(spark: SparkSession) -> None:
    print("\n2. Transaction cut: a loan and its two ledger lines, landing at different moments")
    lineage = "source_incarnation INT, source_lsn BIGINT, is_deleted BOOLEAN, updated_at TIMESTAMP"
    change = "op STRING, source_incarnation INT, source_lsn BIGINT, transaction_id STRING, ingest_ts TIMESTAMP"
    spark.sql("""CREATE TABLE lake.demo.transactions (position BIGINT, transaction_id STRING,
        status STRING, data_collections ARRAY<STRUCT<data_collection: STRING, event_count: BIGINT>>,
        committed_at TIMESTAMP) USING iceberg""")
    spark.sql(
        f"CREATE TABLE lake.demo.bronze_loan (loan_id STRING, status STRING, {change}) USING iceberg"
    )
    spark.sql(
        f"CREATE TABLE lake.demo.bronze_ledger (entry_id STRING, amount_paise BIGINT, {change}) USING iceberg"
    )
    spark.sql(
        f"CREATE TABLE lake.demo.loan (loan_id STRING, status STRING, {lineage}) USING iceberg"
    )
    spark.sql(
        f"CREATE TABLE lake.demo.ledger_entry (entry_id STRING, amount_paise BIGINT, {lineage}) USING iceberg"
    )
    tables = [
        CdcTable(
            "public.loan",
            "lake.demo.bronze_loan",
            MergeSpec("lake.demo.loan", ("loan_id",), ("status",)),
        ),
        CdcTable(
            "public.ledger_entry",
            "lake.demo.bronze_ledger",
            MergeSpec("lake.demo.ledger_entry", ("entry_id",), ("amount_paise",)),
        ),
    ]
    spark.sql("""INSERT INTO lake.demo.transactions VALUES (1, 't1', 'END',
        array(named_struct('data_collection', 'public.loan', 'event_count', 1L),
              named_struct('data_collection', 'public.ledger_entry', 'event_count', 2L)),
        TIMESTAMP '2026-03-02 10:00:00')""")
    spark.sql(
        "INSERT INTO lake.demo.bronze_loan VALUES ('L1', 'DISBURSED', 'c', 1, 101, 't1', current_timestamp())"
    )
    spark.sql(
        "INSERT INTO lake.demo.bronze_ledger VALUES ('E1', -500000, 'c', 1, 102, 't1', current_timestamp())"
    )

    def advance():
        return advance_to_cut(
            spark,
            source="lending",
            transactions_table="lake.demo.transactions",
            tables=tables,
            previous=None,
        )

    say(
        f"loan and one ledger line landed -> cut: {advance()} (silver loan rows: "
        f"{spark.table('lake.demo.loan').count()})"
    )
    spark.sql(
        "INSERT INTO lake.demo.bronze_ledger VALUES ('E2', 500000, 'c', 1, 103, 't1', current_timestamp())"
    )
    cut = advance()
    loans = read_at_cut(spark, "lake.demo.loan", "lending", cut.position).count()
    lines = read_at_cut(spark, "lake.demo.ledger_entry", "lending", cut.position).count()
    say(
        f"second ledger line landed -> cut at position {cut.position}: {loans} loan, {lines} ledger lines"
    )


def publish_gate(spark: SparkSession) -> None:
    print("\n3. Publish gate: money moved between two customers, then a correct build")
    schema = "txn_id STRING, business_line STRING, business_date DATE, amount_paise BIGINT"
    spark.sql(f"CREATE TABLE lake.demo.fact_transaction ({schema}) USING iceberg")
    day = date(2026, 3, 2)
    source = spark.createDataFrame(
        [("t1", "lending", day, 5000), ("t2", "lending", day, 0)], schema
    )
    moved = spark.createDataFrame([("t1", "lending", day, 0), ("t2", "lending", day, 5000)], schema)

    for name, build in (("moved", moved), ("correct", source)):
        branch = f"candidate_{name}"
        write_candidate(
            spark, "lake.demo.fact_transaction", build, branch=branch, dates=[day], version_label={}
        )
        result = publish_or_hold(
            spark,
            "lake.demo.fact_transaction",
            branch=branch,
            dates=[day],
            key_columns=["txn_id"],
            inputs=[InputStatus("lending", complete=True)],
            reference_rows=source,
        )
        verdict = "published" if result.published else f"held: {result.reasons[0]}"
        say(f"{name} build -> {verdict}")


def main() -> None:
    spark = start_spark()
    try:
        partner_files(spark)
        transaction_cut(spark)
        publish_gate(spark)
        print(f"\nTables left in {WAREHOUSE} for inspection.")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
