"""The publish gate: gold becomes readable only when complete and tied to the paise."""

from __future__ import annotations

from datetime import date

import pytest

from lakehouse.models import InputStatus
from lakehouse.publishing.publish_gate import (
    cell_totals,
    compare_totals,
    current_snapshot_id,
    fingerprint_column,
    publish_or_hold,
    read_at_snapshot,
    row_fingerprint,
    write_candidate,
)

pytestmark = pytest.mark.spark

DAY_1, DAY_2 = date(2026, 3, 1), date(2026, 3, 2)
SCHEMA = "txn_id STRING, business_line STRING, business_date DATE, amount_paise BIGINT"
COMPLETE = [InputStatus("lending", complete=True)]


@pytest.fixture
def tables(spark, namespace) -> tuple[str, str]:
    gold, silver = f"{namespace}.fact_transaction", f"{namespace}.transaction"
    for table in (gold, silver):
        spark.sql(f"CREATE TABLE {table} ({SCHEMA}) USING iceberg")
    return gold, silver


def rows(spark, *transactions):
    """Transactions as (txn_id, amount_paise) on day 1 in lending, or full tuples."""
    full = [t if len(t) == 4 else (t[0], "lending", DAY_1, t[1]) for t in transactions]
    return spark.createDataFrame(full, SCHEMA)


def gate(spark, gold, reference_rows, inputs=COMPLETE, dates=(DAY_1,)):
    return publish_or_hold(
        spark,
        gold,
        branch="candidate",
        dates=dates,
        key_columns=["txn_id"],
        inputs=inputs,
        reference_rows=reference_rows,
    )


def build(spark, gold, candidate_rows, dates=(DAY_1,), label=None):
    write_candidate(
        spark, gold, candidate_rows, branch="candidate", dates=dates, version_label=label or {}
    )


def test_money_moved_between_customers_is_caught_only_by_the_fingerprint(spark, tables):
    gold, _ = tables
    source = rows(spark, ("t1", 5_000), ("t2", 0))
    moved = rows(spark, ("t1", 0), ("t2", 5_000))  # same count, total and keys
    build(spark, gold, moved)

    result = gate(spark, gold, reference_rows=source)

    assert not result.published
    assert "fingerprint" in result.reasons[0]
    totals = [cell_totals(df, ["txn_id"]).drop("fingerprint").collect() for df in (source, moved)]
    assert totals[0] == totals[1], "the three plain measures cannot see the move"


def test_an_incomplete_input_holds_the_table_and_readers_keep_the_previous_version(spark, tables):
    gold, _ = tables
    spark.sql(f"INSERT INTO {gold} VALUES ('t0', 'lending', DATE '2026-03-01', 100)")
    build(spark, gold, rows(spark, ("t1", 500)))

    result = gate(
        spark,
        gold,
        reference_rows=rows(spark, ("t1", 500)),
        inputs=[InputStatus("acme.settlement", complete=False, detail="no version for 2026-03-01")],
    )

    assert not result.published and "acme.settlement" in result.reasons[0]
    assert [r.txn_id for r in spark.table(gold).collect()] == ["t0"], "main is untouched"
    assert spark.sql(f"SELECT 1 FROM {gold}.refs WHERE name = 'candidate'").count() == 1


def test_a_clean_build_publishes_with_its_version_label(spark, tables):
    gold, silver = tables
    spark.sql(f"INSERT INTO {silver} VALUES ('t1', 'lending', DATE '2026-03-01', 500)")
    silver_snapshot = current_snapshot_id(spark, silver)
    build(spark, gold, spark.table(silver), label={"silver_snapshot": str(silver_snapshot)})

    result = gate(spark, gold, reference_rows=read_at_snapshot(spark, silver, silver_snapshot))

    assert result.published
    summary = spark.sql(
        f"SELECT summary FROM {gold}.snapshots WHERE snapshot_id = {current_snapshot_id(spark, gold)}"
    ).first()[0]
    assert summary["lakehouse.silver_snapshot"] == str(silver_snapshot)


def test_the_reference_is_silver_as_the_build_read_it_not_silver_now(spark, tables):
    gold, silver = tables
    spark.sql(f"INSERT INTO {silver} VALUES ('t1', 'lending', DATE '2026-03-01', 500)")
    read_by_build = current_snapshot_id(spark, silver)
    build(spark, gold, spark.table(silver))
    spark.sql(f"INSERT INTO {silver} VALUES ('t2', 'lending', DATE '2026-03-01', 700)")  # moved on

    now = cell_totals(spark.table(silver), ["txn_id"])
    assert compare_totals(cell_totals(rows(spark, ("t1", 500)), ["txn_id"]), now), (
        "against today's silver the build would falsely break"
    )
    assert gate(
        spark, gold, reference_rows=read_at_snapshot(spark, silver, read_by_build)
    ).published


def test_a_date_with_no_rows_now_becomes_empty_instead_of_keeping_old_rows(spark, tables):
    gold, _ = tables
    spark.sql(f"""INSERT INTO {gold} VALUES
        ('t1', 'lending', DATE '2026-03-01', 500), ('t9', 'lending', DATE '2026-03-02', 900)""")
    only_day_1 = rows(spark, ("t1", 500))
    build(spark, gold, only_day_1, dates=(DAY_1, DAY_2))

    result = gate(spark, gold, reference_rows=only_day_1, dates=(DAY_1, DAY_2))

    assert result.published
    assert spark.table(gold).where(f"business_date = DATE '{DAY_2}'").count() == 0


def test_a_cell_only_the_build_has_is_a_break(spark, tables):
    gold, _ = tables
    reference = rows(spark, ("t1", 500))
    build(spark, gold, reference.union(rows(spark, ("t1", "lending", DAY_2, 500))), (DAY_1, DAY_2))

    result = gate(spark, gold, reference_rows=reference, dates=(DAY_1, DAY_2))

    assert not result.published, "a day the source never reported, such as a double load"


def test_publishing_is_refused_when_main_moved_after_the_branch_was_cut(spark, tables):
    gold, _ = tables
    build(spark, gold, rows(spark, ("t1", 500)))
    spark.sql(f"INSERT INTO {gold} VALUES ('rogue', 'lending', DATE '2026-03-01', 1)")

    with pytest.raises(Exception, match=r"(?i)fast-forward|ancestor"):
        gate(spark, gold, reference_rows=rows(spark, ("t1", 500)))

    assert [r.txn_id for r in spark.table(gold).collect()] == ["rogue"]


def test_the_spark_fingerprint_matches_the_reference_implementation(spark):
    samples = [("t1", 5_000), ("t2", -45_000), ("ಕನ್ನಡ-7", 0), ("t4", 9_000_000_000_000)]
    frame = rows(spark, *samples).withColumn("fp", fingerprint_column(["txn_id"], "amount_paise"))

    spark_values = {r.txn_id: r.fp for r in frame.collect()}

    assert spark_values == {key: row_fingerprint([key], amount) for key, amount in samples}
