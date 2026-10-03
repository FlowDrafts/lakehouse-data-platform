"""The ordered merge: silver depends only on the source's order, never on arrival order."""

from __future__ import annotations

import pytest

from lakehouse.ingestion.cdc_merge import UNCHANGED_PLACEHOLDER, MergeSpec, merge_changes

pytestmark = pytest.mark.spark

CHANGE_SCHEMA = (
    "loan_id STRING, status STRING, principal_paise BIGINT, loan_terms STRING, "
    "op STRING, source_incarnation INT, source_lsn BIGINT"
)


@pytest.fixture
def loan_table(spark, namespace) -> str:
    table = f"{namespace}.loan"
    spark.sql(f"""
        CREATE TABLE {table} (
          loan_id STRING, status STRING, principal_paise BIGINT, loan_terms STRING,
          source_incarnation INT, source_lsn BIGINT, is_deleted BOOLEAN, updated_at TIMESTAMP
        ) USING iceberg
    """)
    return table


def change(op, lsn, status="APPROVED", principal=100_000, terms="12 months", incarnation=1):
    if op == "d":
        status, principal, terms = None, None, None
    return ("L1", status, principal, terms, op, incarnation, lsn)


def apply_one_by_one(spark, table, *changes):
    """Apply each change as its own batch, in the order given: the real shape of arrival."""
    spec = MergeSpec(
        target_table=table,
        key_columns=("loan_id",),
        value_columns=("status", "principal_paise", "loan_terms"),
        large_columns=("loan_terms",),
    )
    for one in changes:
        merge_changes(spark, spec, spark.createDataFrame([one], CHANGE_SCHEMA))


def the_row(spark, table):
    rows = spark.table(table).collect()
    assert len(rows) == 1, f"expected one row for the key, found {len(rows)}"
    return rows[0]


def test_an_older_change_arriving_late_never_overwrites_a_newer_one(spark, loan_table):
    apply_one_by_one(
        spark,
        loan_table,
        change("c", lsn=10),
        change("u", lsn=30, status="DISBURSED"),
        change("u", lsn=20, status="REJECTED"),  # older, arrives last
    )

    row = the_row(spark, loan_table)
    assert (row.status, row.source_lsn) == ("DISBURSED", 30)


def test_a_deleted_row_stays_deleted_when_an_older_update_arrives_after_it(spark, loan_table):
    apply_one_by_one(
        spark,
        loan_table,
        change("c", lsn=10),
        change("d", lsn=30),
        change("u", lsn=20, status="DISBURSED"),  # older than the delete
    )

    row = the_row(spark, loan_table)
    assert row.is_deleted
    assert row.status is None, "a delete clears the values, whatever arrived before it"


def test_a_delete_that_arrives_before_its_insert_still_wins(spark, loan_table):
    apply_one_by_one(spark, loan_table, change("d", lsn=20), change("c", lsn=10))

    assert the_row(spark, loan_table).is_deleted


def test_a_truncate_fails_the_batch_instead_of_writing_nulls(spark, loan_table):
    apply_one_by_one(spark, loan_table, change("c", lsn=10))

    with pytest.raises(Exception, match="unsupported change operation"):
        apply_one_by_one(spark, loan_table, change("t", lsn=20, status=None))

    assert the_row(spark, loan_table).status == "APPROVED"


def test_a_new_incarnation_outranks_higher_positions_from_before_a_restore(spark, loan_table):
    apply_one_by_one(
        spark,
        loan_table,
        change("u", lsn=900, status="DISBURSED", incarnation=1),
        change("u", lsn=5, status="CLOSED", incarnation=2),  # positions restarted after a restore
        change("u", lsn=950, status="REJECTED", incarnation=1),  # a late replay from before it
    )

    assert the_row(spark, loan_table).status == "CLOSED"


def test_an_unchanged_large_column_keeps_its_value(spark, loan_table):
    apply_one_by_one(
        spark,
        loan_table,
        change("c", lsn=10, terms="12 months"),
        change("u", lsn=20, status="DISBURSED", terms=UNCHANGED_PLACEHOLDER),
    )

    row = the_row(spark, loan_table)
    assert (row.status, row.loan_terms) == ("DISBURSED", "12 months")
