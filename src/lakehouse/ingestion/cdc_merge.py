"""Merge database changes into a silver current-state table, in source order.

Changes arrive at least once and can arrive out of order. The merge makes the result depend
only on the source's own order, never on arrival order:

- A change applies only if it is newer: a higher incarnation, or the same incarnation and a
  higher change-log position (LSN). Replays and late arrivals become no-ops.
- A delete clears the row's values and keeps its key, so a late older change cannot revive it.
- A delete for a key never seen is stored, for the same reason.
- An unsupported operation (a truncate) fails the batch instead of writing nulls.
- An unchanged large column arrives as Debezium's placeholder and never overwrites the value.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

UNCHANGED_PLACEHOLDER = "__debezium_unavailable_value"
SUPPORTED_OPERATIONS = "'c', 'u', 'd', 'r'"
LINEAGE_COLUMNS = ("source_incarnation", "source_lsn", "is_deleted", "updated_at")


@dataclass(frozen=True)
class MergeSpec:
    """How one silver table is merged."""

    target_table: str
    key_columns: tuple[str, ...]
    value_columns: tuple[str, ...]
    # Large text or JSON columns that Postgres leaves out of an update when unchanged.
    large_columns: tuple[str, ...] = ()


def latest_change_per_key(changes: DataFrame, key_columns: tuple[str, ...]) -> DataFrame:
    """Keep only the newest change for each key. A MERGE source may not repeat a key."""
    newest_first = Window.partitionBy(*key_columns).orderBy(
        F.col("source_incarnation").desc(), F.col("source_lsn").desc()
    )
    return (
        changes.withColumn("change_rank", F.row_number().over(newest_first))
        .where("change_rank = 1")
        .drop("change_rank")
    )


def merge_sql(spec: MergeSpec, changes_view: str) -> str:
    """The MERGE statement. Clause order matters: the first matching clause wins."""
    is_newer = (
        "(s.source_incarnation > t.source_incarnation OR "
        "(s.source_incarnation = t.source_incarnation AND s.source_lsn > t.source_lsn))"
    )
    match_keys = " AND ".join(f"t.{c} = s.{c}" for c in spec.key_columns)
    columns = [*spec.key_columns, *spec.value_columns, *LINEAGE_COLUMNS]

    def new_value(column: str) -> str:
        if column in spec.large_columns:
            return f"CASE WHEN s.{column} = '{UNCHANGED_PLACEHOLDER}' THEN t.{column} ELSE s.{column} END"
        return f"s.{column}"

    def inserted_value(column: str) -> str:
        if column in spec.large_columns:
            return f"nullif(s.{column}, '{UNCHANGED_PLACEHOLDER}')"
        return f"s.{column}"

    keys = [f"s.{c}" for c in spec.key_columns]
    lineage = "s.source_incarnation, s.source_lsn"
    update_values = ", ".join(f"t.{c} = {new_value(c)}" for c in spec.value_columns)
    clear_values = ", ".join(f"t.{c} = NULL" for c in spec.value_columns)
    live_row = ", ".join(
        [
            *keys,
            *(inserted_value(c) for c in spec.value_columns),
            lineage,
            "false",
            "current_timestamp()",
        ]
    )
    deleted_row = ", ".join(
        [*keys, *(["NULL"] * len(spec.value_columns)), lineage, "true", "current_timestamp()"]
    )
    unsupported = "raise_error(concat('unsupported change operation: ', s.op))"
    failing_row = ", ".join([unsupported, *(["NULL"] * (len(columns) - 1))])
    set_lineage = (
        "t.source_incarnation = s.source_incarnation, t.source_lsn = s.source_lsn, "
        "t.updated_at = current_timestamp()"
    )

    return f"""
MERGE INTO {spec.target_table} AS t
USING {changes_view} AS s
ON {match_keys}
WHEN MATCHED AND s.op NOT IN ({SUPPORTED_OPERATIONS}) THEN
  UPDATE SET t.{spec.key_columns[0]} = {unsupported}
WHEN MATCHED AND s.op = 'd' AND {is_newer} THEN
  UPDATE SET {clear_values}, t.is_deleted = true, {set_lineage}
WHEN MATCHED AND {is_newer} THEN
  UPDATE SET {update_values}, t.is_deleted = false, {set_lineage}
WHEN NOT MATCHED AND s.op NOT IN ({SUPPORTED_OPERATIONS}) THEN
  INSERT ({", ".join(columns)}) VALUES ({failing_row})
WHEN NOT MATCHED AND s.op = 'd' THEN
  INSERT ({", ".join(columns)}) VALUES ({deleted_row})
WHEN NOT MATCHED THEN
  INSERT ({", ".join(columns)}) VALUES ({live_row})
"""


def merge_changes(spark: SparkSession, spec: MergeSpec, changes: DataFrame) -> None:
    """Apply a batch of changes to the target table."""
    view = "changes_" + spec.target_table.replace(".", "_")
    # Materialised first: Spark 4.1 cannot plan a MERGE whose source view still reads another
    # Iceberg table, and the batch is small and read only once.
    batch = latest_change_per_key(changes, spec.key_columns).localCheckpoint()
    batch.createOrReplaceTempView(view)
    spark.sql(merge_sql(spec, view))
