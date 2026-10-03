"""Partner file deliveries: which version is the truth, and is it whole?

A delivery is one (partner, feed, posting date). A partner may send it in several parts, send a
part again, correct it with a new version, send an older version late, or truncate it. Each
part can tie to its own trailer while the delivery as a whole is wrong. The guarantees:

- A version publishes only when every part in its manifest has arrived and passed its checks,
  so parts of two versions are never mixed.
- Versions are ordered by the partner's sequence number, never by a timestamp, and an older
  version never replaces a newer one, however the publishes race.
- A part's rows are loaded exactly once, even after a crash or when two workers race.
- A version far smaller than the same weekday in recent weeks is held for approval.
- Every change of the current version is kept, so any past state can be read back.
"""

from __future__ import annotations

import enum
import re
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TypeVar

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from lakehouse.models import InputStatus

# Identifiers that come from partners are checked here, at the boundary, so that nothing a
# partner sends can change the meaning of the SQL built from it.
SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
T = TypeVar("T")


def require_safe(**values: str) -> None:
    for name, value in values.items():
        if not SAFE_IDENTIFIER.fullmatch(value):
            raise ValueError(f"{name} {value!r} has characters outside [A-Za-z0-9._:-]")


class PartState(enum.StrEnum):
    STAGED = "STAGED"  # checked and loaded; invisible until its version publishes
    REJECTED = "REJECTED"  # failed a check; nothing loaded
    DUPLICATE = "DUPLICATE"  # this part of this version was already received
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"


class PublishResult(enum.StrEnum):
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"  # an equal or newer version is already current
    INCOMPLETE = "INCOMPLETE"  # parts of the manifest are still missing
    HELD_FOR_APPROVAL = "HELD_FOR_APPROVAL"  # far smaller than usual; possibly truncated


@dataclass(frozen=True)
class Delivery:
    partner: str
    feed: str
    posting_date: date

    def __post_init__(self) -> None:
        require_safe(partner=self.partner, feed=self.feed)

    def where(self, alias: str = "") -> str:
        prefix = f"{alias}." if alias else ""
        return (
            f"{prefix}partner = '{self.partner}' AND {prefix}feed = '{self.feed}' "
            f"AND {prefix}posting_date = DATE '{self.posting_date}'"
        )


@dataclass(frozen=True)
class FilePart:
    """One received file: which part of which version of which delivery, and its trailer."""

    file_id: str
    file_hash: str
    delivery: Delivery
    sequence_number: int
    part_number: int
    part_count: int
    trailer_row_count: int
    trailer_amount_paise: int

    def __post_init__(self) -> None:
        require_safe(file_id=self.file_id, file_hash=self.file_hash)


@dataclass(frozen=True)
class FeedContract:
    key_columns: tuple[str, ...]
    amount_column: str = "amount_paise"
    truncation_threshold: float = 0.2  # hold a version with this much fewer rows than usual


@dataclass(frozen=True)
class PartnerFileTables:
    register: str  # one row per received file
    rows: str  # every row of every version, tagged with its version
    pointer: str  # which version is current for each delivery, with full history


def check_part(rows: DataFrame, part: FilePart, contract: FeedContract) -> list[str]:
    """Check the whole part before anything is written. Returns the problems found."""
    totals = rows.agg(
        F.count(F.lit(1)).alias("row_count"),
        F.sum(contract.amount_column).alias("amount_paise"),
        F.count_distinct(*contract.key_columns).alias("distinct_keys"),
        F.count_if(F.col(contract.amount_column).isNull()).alias("null_amounts"),
        F.count_if(F.col("posting_date") != F.lit(part.delivery.posting_date)).alias("other_dates"),
    ).first()

    problems = []
    if totals["row_count"] != part.trailer_row_count:
        problems.append(f"{totals['row_count']} rows, trailer says {part.trailer_row_count}")
    if (totals["amount_paise"] or 0) != part.trailer_amount_paise:
        problems.append(f"{totals['amount_paise']} paise, trailer says {part.trailer_amount_paise}")
    if totals["distinct_keys"] != totals["row_count"]:
        problems.append("duplicate or null keys")
    if totals["null_amounts"]:
        problems.append(f"{totals['null_amounts']} rows without an amount")
    if totals["other_dates"]:
        problems.append(f"{totals['other_dates']} rows for another posting date")
    return problems


class PartnerFileLoader:
    def __init__(self, spark: SparkSession, tables: PartnerFileTables, contract: FeedContract):
        self.spark = spark
        self.tables = tables
        self.contract = contract

    def receive(self, part: FilePart, rows: DataFrame) -> PartState:
        """Register, check and load one part. Nothing is visible until its version publishes."""
        if self._already_received(part):
            return PartState.DUPLICATE
        problems = check_part(rows, part, self.contract)
        if problems:
            self._record(part, PartState.REJECTED, "; ".join(problems))
            return PartState.REJECTED
        self.load(part, rows)
        self._record(part, PartState.STAGED)
        return PartState.STAGED

    def load(self, part: FilePart, rows: DataFrame) -> None:
        """Load the part's rows by replacing whatever rows carry its file id.

        A replace is idempotent, so a rerun after a crash loads nothing twice. Two workers
        loading the same part at once conflict at commit, and the retry replaces again. The
        rows table keeps exact bounds on file_id, so a replace touches only that file's data.
        """
        d = part.delivery
        tagged = rows.select(
            F.lit(d.partner).alias("partner"),
            F.lit(d.feed).alias("feed"),
            F.lit(part.sequence_number).cast("bigint").alias("sequence_number"),
            F.lit(part.file_id).alias("file_id"),
            *rows.columns,
        )
        self._retry(
            lambda: tagged.writeTo(self.tables.rows).overwrite(F.col("file_id") == part.file_id)
        )

    def publish(
        self, delivery: Delivery, sequence_number: int, approved_by: str | None = None
    ) -> PublishResult:
        """Make a version current, if it is whole, newer than the current one, and not suspect."""
        parts = self._sql(f"""
            SELECT part_count, row_count FROM {self.tables.register}
            WHERE {delivery.where()} AND sequence_number = {sequence_number}
              AND state IN ('STAGED', 'PUBLISHED')
        """).collect()
        if not parts:
            current = self._current_sequence(delivery)
            newer_is_current = current is not None and current >= sequence_number
            return PublishResult.SUPERSEDED if newer_is_current else PublishResult.INCOMPLETE
        if len(parts) < parts[0]["part_count"]:
            return PublishResult.INCOMPLETE

        usual = self._usual_row_count(delivery)
        threshold = 1 - self.contract.truncation_threshold
        if approved_by is None and usual and sum(p["row_count"] for p in parts) < usual * threshold:
            return PublishResult.HELD_FOR_APPROVAL

        self._flip_pointer(delivery, sequence_number, approved_by)
        published = self._current_sequence(delivery) == sequence_number
        self._sql(f"""
            UPDATE {self.tables.register}
            SET state = CASE WHEN sequence_number = {sequence_number} AND {published}
                             THEN 'PUBLISHED' ELSE 'SUPERSEDED' END
            WHERE {delivery.where()} AND sequence_number <= {sequence_number}
              AND state IN ('STAGED', 'PUBLISHED')
        """)
        return PublishResult.PUBLISHED if published else PublishResult.SUPERSEDED

    def input_status(self, delivery: Delivery) -> InputStatus:
        """A delivery is complete for the publish gate once some version of it is current."""
        name = f"{delivery.partner}.{delivery.feed}"
        if self._current_sequence(delivery) is None:
            return InputStatus(
                name, complete=False, detail=f"no version for {delivery.posting_date}"
            )
        return InputStatus(name, complete=True)

    def current_rows(self) -> DataFrame:
        """The rows of the current version of every delivery."""
        return self._rows_where("p.valid_to IS NULL")

    def rows_as_known_at(self, moment: datetime) -> DataFrame:
        """The rows of whichever version was current at that moment (timezone-aware)."""
        if moment.tzinfo is None:
            raise ValueError("pass a timezone-aware moment; the lake stores UTC")
        at = f"TIMESTAMP '{moment.astimezone(UTC):%Y-%m-%d %H:%M:%S.%f}'"
        return self._rows_where(
            f"p.valid_from <= {at} AND (p.valid_to IS NULL OR p.valid_to > {at})"
        )

    # ----------------------------------------------------------------------------------------

    def _flip_pointer(
        self, delivery: Delivery, sequence_number: int, approved_by: str | None
    ) -> None:
        """Compare-and-set, decided inside one MERGE.

        The new version is inserted, and the current one closed, only if the new sequence
        number is higher. Two racing publishes conflict at commit; the retry decides again.
        """
        if approved_by:
            require_safe(approved_by=approved_by)
        approver = f"'{approved_by}'" if approved_by else "CAST(NULL AS STRING)"
        current = (
            f"SELECT coalesce(max(sequence_number), -1) FROM {self.tables.pointer} "
            f"WHERE {delivery.where()} AND valid_to IS NULL"
        )
        self._sql(f"""
            MERGE INTO {self.tables.pointer} AS t
            USING (
              SELECT '{delivery.partner}' AS partner, '{delivery.feed}' AS feed,
                     DATE '{delivery.posting_date}' AS posting_date,
                     CAST({sequence_number} AS BIGINT) AS sequence_number,
                     {approver} AS approved_by, ({current}) AS current_sequence
            ) AS s
            ON t.partner = s.partner AND t.feed = s.feed AND t.posting_date = s.posting_date
               AND t.sequence_number = s.sequence_number AND t.valid_to IS NULL
            WHEN NOT MATCHED AND s.sequence_number > s.current_sequence THEN
              INSERT (partner, feed, posting_date, sequence_number, valid_from, valid_to, approved_by)
              VALUES (s.partner, s.feed, s.posting_date, s.sequence_number,
                      current_timestamp(), NULL, s.approved_by)
            WHEN NOT MATCHED BY SOURCE AND {delivery.where("t")}
                 AND t.valid_to IS NULL AND t.sequence_number < {sequence_number} THEN
              UPDATE SET t.valid_to = current_timestamp()
        """)

    def _usual_row_count(self, delivery: Delivery) -> float | None:
        """Median published row count for the same weekday over the last four weeks."""
        weeks = ", ".join(
            f"DATE '{delivery.posting_date - timedelta(weeks=w)}'" for w in range(1, 5)
        )
        counts = self._sql(f"""
            SELECT sum(r.row_count) AS row_count
            FROM {self.tables.pointer} p JOIN {self.tables.register} r
              ON r.partner = p.partner AND r.feed = p.feed AND r.posting_date = p.posting_date
             AND r.sequence_number = p.sequence_number AND r.state = 'PUBLISHED'
            WHERE p.partner = '{delivery.partner}' AND p.feed = '{delivery.feed}'
              AND p.valid_to IS NULL AND p.posting_date IN ({weeks})
            GROUP BY p.posting_date
        """).collect()
        return statistics.median(r["row_count"] for r in counts) if counts else None

    def _already_received(self, part: FilePart) -> bool:
        return bool(
            self._sql(f"""
                SELECT 1 FROM {self.tables.register}
                WHERE state IN ('STAGED', 'PUBLISHED', 'SUPERSEDED')
                  AND (file_hash = '{part.file_hash}'
                       OR ({part.delivery.where()} AND sequence_number = {part.sequence_number}
                           AND part_number = {part.part_number}))
            """).first()
        )

    def _record(self, part: FilePart, state: PartState, reason: str = "") -> None:
        d = part.delivery
        reason = reason.replace("'", "")  # our own text, but never let it end the literal
        self._sql(f"""
            MERGE INTO {self.tables.register} AS t
            USING (SELECT '{part.file_id}' AS file_id) AS s ON t.file_id = s.file_id
            WHEN MATCHED THEN UPDATE SET t.state = '{state}', t.reason = '{reason}'
            WHEN NOT MATCHED THEN INSERT (
              file_id, file_hash, partner, feed, posting_date, sequence_number, part_number,
              part_count, row_count, amount_paise, state, reason, registered_at
            ) VALUES (
              '{part.file_id}', '{part.file_hash}', '{d.partner}', '{d.feed}',
              DATE '{d.posting_date}', {part.sequence_number}, {part.part_number},
              {part.part_count}, {part.trailer_row_count}, {part.trailer_amount_paise},
              '{state}', '{reason}', current_timestamp()
            )
        """)

    def _current_sequence(self, delivery: Delivery) -> int | None:
        return self._sql(
            f"SELECT max(sequence_number) AS seq FROM {self.tables.pointer} "
            f"WHERE {delivery.where()} AND valid_to IS NULL"
        ).first()["seq"]

    def _rows_where(self, pointer_condition: str) -> DataFrame:
        return self._sql(f"""
            SELECT r.* FROM {self.tables.rows} r JOIN {self.tables.pointer} p
              ON r.partner = p.partner AND r.feed = p.feed AND r.posting_date = p.posting_date
             AND r.sequence_number = p.sequence_number
            WHERE {pointer_condition}
        """)

    def _sql(self, statement: str) -> DataFrame:
        return self._retry(lambda: self.spark.sql(statement))

    def _retry(self, action: Callable[[], T], attempts: int = 5) -> T:
        """Run an action, retrying when a concurrent commit won the race."""
        for attempt in range(attempts):
            try:
                return action()
            except Exception as error:
                conflict = any(
                    w in str(error).lower() for w in ("conflict", "commit", "concurrent")
                )
                if not conflict or attempt == attempts - 1:
                    raise
        raise AssertionError("unreachable")
