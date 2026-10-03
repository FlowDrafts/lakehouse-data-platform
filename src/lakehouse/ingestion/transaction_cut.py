"""A consistent, complete cut across every table of one source database.

One Postgres transaction, such as a loan and its two ledger lines, reaches the lake as events
on different topics and partitions that land at different moments. Merged as they land, silver
briefly holds the loan without its ledger lines, and gold built at that moment ties to silver
while being wrong. Per partition, "has the day been read past its cut-off?" cannot be answered
either: an idle partition and a lagging one look the same.

Debezium's transaction metadata settles both. Each transaction's END record, on a
single-partition topic in commit order, states how many events it produced for each table. A
transaction has landed when bronze holds exactly that many. The cut is the longest prefix of
landed transactions. Silver advances only to the cut, for every table of the source together,
and each table is tagged so that gold reads all of them at the same cut.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from lakehouse.ingestion.cdc_merge import MergeSpec, merge_changes
from lakehouse.models import InputStatus

# Bronze ingest time and source commit time come from different clocks.
CLOCK_ALLOWANCE = timedelta(minutes=10)


@dataclass(frozen=True)
class TransactionEnd:
    """One END record from Debezium's transaction topic."""

    position: int  # offset on the single-partition transaction topic, which is commit order
    transaction_id: str
    committed_at: datetime
    event_counts: Mapping[str, int]  # source table -> events the transaction produced


@dataclass(frozen=True)
class CdcTable:
    """One captured source table: where its changes land, and how they merge into silver."""

    source_table: str  # as Debezium names it, e.g. "public.loan"
    bronze_table: str
    merge: MergeSpec


def find_cut(
    ends: Sequence[TransactionEnd], landed: Mapping[tuple[str, str], int]
) -> TransactionEnd | None:
    """The last transaction of the longest prefix whose events have all landed.

    `landed` maps (transaction_id, source_table) to the number of distinct events in bronze.
    A complete transaction after an incomplete one is not included: it may depend on it.
    """
    cut = None
    for end in sorted(ends, key=lambda e: e.position):
        if any(landed.get((end.transaction_id, t), 0) != n for t, n in end.event_counts.items()):
            break
        cut = end
    return cut


def input_status(source: str, cut: TransactionEnd | None, cutoff: datetime) -> InputStatus:
    """A business date is complete once the cut holds a transaction committed after its cut-off.

    Debezium heartbeats write a small transaction regularly, so an idle source still passes.
    """
    if cut is not None and cut.committed_at >= cutoff:
        return InputStatus(source, complete=True)
    reached = cut.committed_at.isoformat() if cut else "nothing yet"
    return InputStatus(source, complete=False, detail=f"cut has reached {reached}")


def cut_tag(source: str, position: int) -> str:
    return f"cut_{source}_{position}"


def read_at_cut(spark: SparkSession, table: str, source: str, position: int) -> DataFrame:
    """Read a silver table exactly as it stood at a cut, whatever has merged since."""
    return spark.sql(f"SELECT * FROM {table} VERSION AS OF '{cut_tag(source, position)}'")


def advance_to_cut(
    spark: SparkSession,
    *,
    source: str,
    transactions_table: str,
    tables: Sequence[CdcTable],
    previous: TransactionEnd | None,
) -> TransactionEnd | None:
    """Merge every table of the source up to the newest complete cut, and tag each table.

    Reads only what is new since the previous cut: its END records, and bronze rows that landed
    after it committed (less a clock allowance), since a later transaction's events can only
    land after that. Safe to rerun. Returns the new cut, or None when nothing new has landed.
    """
    ends = _transaction_ends(spark, transactions_table, previous.position if previous else -1)
    if not ends:
        return None
    since = previous.committed_at - CLOCK_ALLOWANCE if previous else None
    new_ids = _ids_frame(spark, ends)
    changes = {
        table: _landed_since(spark, table, since).join(new_ids, "transaction_id")
        for table in tables
    }

    cut = find_cut(ends, _landed_event_counts(changes))
    if cut is None:
        return None
    in_cut = _ids_frame(spark, [e for e in ends if e.position <= cut.position])
    for table, table_changes in changes.items():
        merge_changes(spark, table.merge, table_changes.join(in_cut, "transaction_id"))
        tag = cut_tag(source, cut.position)
        spark.sql(
            f"ALTER TABLE {table.merge.target_table} CREATE TAG IF NOT EXISTS {tag} RETAIN 7 DAYS"
        )
    return cut


def _transaction_ends(spark: SparkSession, table: str, after_position: int) -> list[TransactionEnd]:
    rows = (
        spark.table(table)
        .where((F.col("status") == "END") & (F.col("position") > after_position))
        .collect()
    )
    return [
        TransactionEnd(
            position=row["position"],
            transaction_id=row["transaction_id"],
            committed_at=row["committed_at"],
            event_counts={c["data_collection"]: c["event_count"] for c in row["data_collections"]},
        )
        for row in rows
    ]


def _ids_frame(spark: SparkSession, ends: Sequence[TransactionEnd]) -> DataFrame:
    return spark.createDataFrame([(e.transaction_id,) for e in ends], "transaction_id STRING")


def _landed_since(spark: SparkSession, table: CdcTable, since: datetime | None) -> DataFrame:
    bronze = spark.table(table.bronze_table)
    return bronze if since is None else bronze.where(F.col("ingest_ts") >= F.lit(since))


def _landed_event_counts(changes: Mapping[CdcTable, DataFrame]) -> dict[tuple[str, str], int]:
    """Distinct events per (transaction, table). Distinct, because delivery repeats."""
    counts: dict[tuple[str, str], int] = {}
    for table, table_changes in changes.items():
        for row in (
            table_changes.groupBy("transaction_id")
            .agg(F.count_distinct("source_lsn").alias("events"))
            .collect()
        ):
            counts[(row["transaction_id"], table.source_table)] = row["events"]
    return counts
