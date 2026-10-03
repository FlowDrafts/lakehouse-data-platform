"""The transaction cut: silver advances only to a point where every transaction is whole."""

from __future__ import annotations

from datetime import datetime

import pytest

from lakehouse.ingestion.cdc_merge import MergeSpec
from lakehouse.ingestion.transaction_cut import (
    CdcTable,
    TransactionEnd,
    advance_to_cut,
    find_cut,
    input_status,
    read_at_cut,
)

LOAN, LEDGER = "public.loan", "public.ledger_entry"


def transaction(position: int, txn_id: str, committed_at: datetime, **counts) -> TransactionEnd:
    tables = {"loan": LOAN, "ledger": LEDGER, "heartbeat": "public.heartbeat"}
    return TransactionEnd(position, txn_id, committed_at, {tables[k]: n for k, n in counts.items()})


def test_a_transaction_enters_the_cut_only_when_every_table_has_all_its_events():
    disbursal = transaction(1, "t1", datetime(2026, 3, 2, 10), loan=1, ledger=2)
    landed = {("t1", LOAN): 1, ("t1", LEDGER): 1}  # one ledger line still in flight

    assert find_cut([disbursal], landed) is None

    landed[("t1", LEDGER)] = 2
    assert find_cut([disbursal], landed) == disbursal


def test_the_cut_stops_at_the_first_incomplete_transaction_even_if_later_ones_landed():
    first = transaction(1, "t1", datetime(2026, 3, 2, 10), loan=1)
    second = transaction(2, "t2", datetime(2026, 3, 2, 11), loan=1, ledger=2)
    third = transaction(3, "t3", datetime(2026, 3, 2, 12), loan=1)
    landed = {("t1", LOAN): 1, ("t2", LOAN): 1, ("t2", LEDGER): 1, ("t3", LOAN): 1}

    assert find_cut([third, first, second], landed) == first


def test_a_date_is_complete_only_once_the_cut_passes_its_cutoff():
    cutoff = datetime(2026, 3, 3)  # midnight, end of 2 March
    last_business_change = transaction(1, "t1", datetime(2026, 3, 2, 23, 58), loan=1)
    heartbeat = transaction(2, "t2", datetime(2026, 3, 3, 0, 0, 10), heartbeat=1)

    assert not input_status("lending", last_business_change, cutoff).complete
    assert input_status("lending", heartbeat, cutoff).complete


@pytest.mark.spark
def test_gold_never_sees_a_loan_without_its_ledger_lines(spark, namespace):
    tables = create_lending_tables(spark, namespace)
    end_record(spark, namespace, 1, "t1", loans=1, ledger_lines=2)
    land(spark, namespace, "bronze_loan", "('L1', 'DISBURSED', 500000, 'c', 1, 101, 't1')")
    land(spark, namespace, "bronze_ledger", "('E1', 'L1', -500000, 'c', 1, 102, 't1')")

    # The second ledger line is still in flight, so nothing may advance.
    assert advance(spark, namespace, tables, previous=None) is None
    assert spark.table(f"{namespace}.loan").count() == 0

    land(spark, namespace, "bronze_ledger", "('E2', 'L1', 500000, 'c', 1, 103, 't1')")
    first = advance(spark, namespace, tables, previous=None)
    assert first is not None and first.position == 1
    assert read_at_cut(spark, f"{namespace}.loan", "lending", 1).count() == 1
    assert read_at_cut(spark, f"{namespace}.ledger_entry", "lending", 1).count() == 2

    # The next transaction is read incrementally, from the previous cut.
    end_record(spark, namespace, 2, "t2", loans=1, ledger_lines=1)
    land(spark, namespace, "bronze_loan", "('L2', 'DISBURSED', 300000, 'c', 1, 201, 't2')")
    land(spark, namespace, "bronze_ledger", "('E3', 'L2', -300000, 'c', 1, 202, 't2')")
    second = advance(spark, namespace, tables, previous=first)
    assert second is not None and second.position == 2
    assert read_at_cut(spark, f"{namespace}.loan", "lending", 2).count() == 2
    assert read_at_cut(spark, f"{namespace}.loan", "lending", 1).count() == 1, "cut 1 is unchanged"


@pytest.mark.spark
def test_rerunning_a_cut_after_a_failure_is_safe(spark, namespace):
    tables = create_lending_tables(spark, namespace)
    end_record(spark, namespace, 1, "t1", loans=1, ledger_lines=1)
    land(spark, namespace, "bronze_loan", "('L1', 'DISBURSED', 500000, 'c', 1, 101, 't1')")
    land(spark, namespace, "bronze_ledger", "('E1', 'L1', -500000, 'c', 1, 102, 't1')")
    advance(spark, namespace, tables, previous=None)

    rerun = advance(
        spark, namespace, tables, previous=None
    )  # as if the first run died after tagging

    assert rerun is not None and rerun.position == 1
    assert read_at_cut(spark, f"{namespace}.ledger_entry", "lending", 1).count() == 1


# --------------------------------------------------------------------------------------------


def advance(spark, namespace, tables, previous):
    return advance_to_cut(
        spark,
        source="lending",
        transactions_table=f"{namespace}.transactions",
        tables=tables,
        previous=previous,
    )


def end_record(spark, namespace, position, txn_id, loans, ledger_lines):
    """Debezium's END record: how many events the transaction produced for each table."""
    spark.sql(f"""
        INSERT INTO {namespace}.transactions VALUES ({position}, '{txn_id}', 'END',
          array(named_struct('data_collection', '{LOAN}', 'event_count', {loans}L),
                named_struct('data_collection', '{LEDGER}', 'event_count', {ledger_lines}L)),
          TIMESTAMP '2026-03-02 10:00:00' + make_interval(0, 0, 0, 0, 0, {position}, 0))
    """)


def land(spark, namespace, bronze_table, values):
    """One change event landing in bronze now."""
    row = values.rstrip(")") + ", current_timestamp())"
    spark.sql(f"INSERT INTO {namespace}.{bronze_table} VALUES {row}")


def create_lending_tables(spark, namespace) -> list[CdcTable]:
    change_columns = "op STRING, source_incarnation INT, source_lsn BIGINT"
    landed = "transaction_id STRING, ingest_ts TIMESTAMP"
    lineage = "source_incarnation INT, source_lsn BIGINT, is_deleted BOOLEAN, updated_at TIMESTAMP"
    spark.sql(f"""CREATE TABLE {namespace}.transactions (
        position BIGINT, transaction_id STRING, status STRING,
        data_collections ARRAY<STRUCT<data_collection: STRING, event_count: BIGINT>>,
        committed_at TIMESTAMP) USING iceberg""")
    spark.sql(f"""CREATE TABLE {namespace}.bronze_loan (loan_id STRING, status STRING,
        principal_paise BIGINT, {change_columns}, {landed}) USING iceberg""")
    spark.sql(f"""CREATE TABLE {namespace}.bronze_ledger (entry_id STRING, loan_id STRING,
        amount_paise BIGINT, {change_columns}, {landed}) USING iceberg""")
    spark.sql(f"""CREATE TABLE {namespace}.loan (loan_id STRING, status STRING,
        principal_paise BIGINT, {lineage}) USING iceberg""")
    spark.sql(f"""CREATE TABLE {namespace}.ledger_entry (entry_id STRING, loan_id STRING,
        amount_paise BIGINT, {lineage}) USING iceberg""")
    return [
        CdcTable(
            LOAN,
            f"{namespace}.bronze_loan",
            MergeSpec(f"{namespace}.loan", ("loan_id",), ("status", "principal_paise")),
        ),
        CdcTable(
            LEDGER,
            f"{namespace}.bronze_ledger",
            MergeSpec(f"{namespace}.ledger_entry", ("entry_id",), ("loan_id", "amount_paise")),
        ),
    ]
