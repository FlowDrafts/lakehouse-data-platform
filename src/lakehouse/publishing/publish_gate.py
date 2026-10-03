"""Publish a gold table only when it is complete and ties to the paise.

A gold build is written to a branch that readers cannot see. Main is fast-forwarded to the
branch only if:

- every declared input reports itself complete, by its own source's signal; and
- for every business line and date, four measures equal the reference exactly: the row count,
  the signed paise total, the number of distinct keys, and a content fingerprint.

Otherwise main is untouched, readers keep the previous version, and the branch is kept for
investigation. The reference is pinned: intraday it is silver at the snapshot the build read,
recorded in the version label; once a date closes it is the source's own control totals.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F

from lakehouse.models import InputStatus

log = logging.getLogger(__name__)

CELL_COLUMNS = ("business_line", "business_date")
MEASURES = ("row_count", "amount_paise", "distinct_keys", "fingerprint")

# The same fingerprint, computed by the source database for its control totals. Both sides hash
# the same text (key and amount joined by '|') and keep the first 32 bits, so a sum over 500M
# rows stays far inside BIGINT and can never overflow.
POSTGRES_FINGERPRINT_SQL = (
    "sum(('x' || lpad(substr(md5(concat_ws('|', {key}, {amount}::text)), 1, 8), 16, '0'))"
    "::bit(64)::bigint)"
)


@dataclass(frozen=True)
class GateResult:
    published: bool
    reasons: tuple[str, ...] = ()


def row_fingerprint(key_values: Sequence[str], amount_paise: int) -> int:
    """Reference implementation of one row's fingerprint, matching Spark and Postgres."""
    text = "|".join([*key_values, str(amount_paise)])
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)


def fingerprint_column(key_columns: Sequence[str], amount_column: str) -> Column:
    text = F.concat_ws(
        "|", *(F.col(c).cast("string") for c in key_columns), F.col(amount_column).cast("string")
    )
    return F.conv(F.substring(F.md5(text), 1, 8), 16, 10).cast("bigint")


def cell_totals(
    rows: DataFrame, key_columns: Sequence[str], amount_column: str = "amount_paise"
) -> DataFrame:
    """The four measures for each (business line, date). Every side is reduced to this."""
    return rows.groupBy(*CELL_COLUMNS).agg(
        F.count(F.lit(1)).alias("row_count"),
        F.sum(amount_column).cast("bigint").alias("amount_paise"),
        F.count_distinct(*key_columns).alias("distinct_keys"),
        F.sum(fingerprint_column(key_columns, amount_column)).alias("fingerprint"),
    )


def compare_totals(candidate: DataFrame, reference: DataFrame) -> list[str]:
    """Every cell where the two sides differ, including a cell that exists on only one side."""
    same = F.lit(True)
    for measure in MEASURES:
        same = same & F.col(f"c.{measure}").eqNullSafe(F.col(f"r.{measure}"))
    differing = candidate.alias("c").join(reference.alias("r"), list(CELL_COLUMNS), "full_outer")
    return [
        f"{row['business_line']} {row['business_date']}: "
        + ", ".join(f"{m} {row[f'c_{m}']} vs {row[f'r_{m}']}" for m in MEASURES)
        for row in differing.where(~same)
        .select(
            *CELL_COLUMNS,
            *(F.col(f"c.{m}").alias(f"c_{m}") for m in MEASURES),
            *(F.col(f"r.{m}").alias(f"r_{m}") for m in MEASURES),
        )
        .collect()
    ]


def write_candidate(
    spark: SparkSession,
    table: str,
    rows: DataFrame,
    *,
    branch: str,
    dates: Iterable[date],
    version_label: Mapping[str, str],
) -> None:
    """Replace the whole date window on a new branch, with the version label on that commit.

    The whole window is replaced, so a date that now has no rows becomes empty. The label is a
    write option, so it is stamped on this commit only.
    """
    in_window = F.col("business_date").isin(list(dates))
    spark.sql(f"ALTER TABLE {table} CREATE BRANCH {branch}")
    writer = rows.where(in_window).writeTo(f"{table}.branch_{branch}")
    for key, value in version_label.items():
        writer = writer.option(f"snapshot-property.lakehouse.{key}", value)
    writer.overwrite(in_window)


def read_at_snapshot(spark: SparkSession, table: str, snapshot_id: int) -> DataFrame:
    return spark.sql(f"SELECT * FROM {table} VERSION AS OF {snapshot_id}")


def current_snapshot_id(spark: SparkSession, table: str) -> int:
    return spark.sql(f"SELECT snapshot_id FROM {table}.refs WHERE name = 'main'").first()[0]


def publish_or_hold(
    spark: SparkSession,
    table: str,
    *,
    branch: str,
    dates: Iterable[date],
    key_columns: Sequence[str],
    inputs: Sequence[InputStatus],
    reference_rows: DataFrame,
) -> GateResult:
    """Check the branch and publish it, or hold it and say why.

    Publishing fast-forwards main to the branch in one step, and Iceberg refuses if main has
    moved since the branch was cut, so a second writer is never silently overwritten.
    """
    reasons = [f"input not complete: {i.name} ({i.detail})" for i in inputs if not i.complete]
    if not reasons:
        window = F.col("business_date").isin(list(dates))
        candidate_rows = spark.table(f"{table}.branch_{branch}").where(window)
        reasons = compare_totals(
            cell_totals(candidate_rows, key_columns),
            cell_totals(reference_rows.where(window), key_columns),
        )
    if reasons:
        return GateResult(published=False, reasons=tuple(reasons))

    catalog, identifier = table.split(".", 1)
    spark.sql(f"CALL {catalog}.system.fast_forward('{identifier}', 'main', '{branch}')")
    try:  # the publish is done; a branch left behind is untidy, not wrong
        spark.sql(f"ALTER TABLE {table} DROP BRANCH {branch}")
    except Exception:
        log.warning("published %s but could not drop branch %s", table, branch)
    return GateResult(published=True)
