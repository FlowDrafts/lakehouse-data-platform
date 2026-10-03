"""Partner files: one current version per delivery, never older, never mixed, never twice."""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime, timedelta

import pytest

from lakehouse.ingestion.partner_files import (
    Delivery,
    FeedContract,
    FilePart,
    PartnerFileLoader,
    PartnerFileTables,
    PartState,
    PublishResult,
)

pytestmark = pytest.mark.spark

MONDAY = date(2026, 3, 2)
DELIVERY = Delivery("acme", "settlement", MONDAY)


@pytest.fixture
def loader(spark, namespace) -> PartnerFileLoader:
    tables = PartnerFileTables(
        register=f"{namespace}.file_register",
        rows=f"{namespace}.settlement_versions",
        pointer=f"{namespace}.file_pointer",
    )
    spark.sql(f"""CREATE TABLE {tables.register} (
        file_id STRING, file_hash STRING, partner STRING, feed STRING, posting_date DATE,
        sequence_number BIGINT, part_number INT, part_count INT, row_count BIGINT,
        amount_paise BIGINT, state STRING, reason STRING, registered_at TIMESTAMP)
        USING iceberg PARTITIONED BY (partner)""")
    spark.sql(f"""CREATE TABLE {tables.rows} (
        partner STRING, feed STRING, sequence_number BIGINT, file_id STRING,
        settlement_id STRING, amount_paise BIGINT, posting_date DATE)
        USING iceberg PARTITIONED BY (partner, posting_date)
        TBLPROPERTIES ('write.metadata.metrics.column.file_id' = 'full')""")
    spark.sql(f"""CREATE TABLE {tables.pointer} (
        partner STRING, feed STRING, posting_date DATE, sequence_number BIGINT,
        valid_from TIMESTAMP, valid_to TIMESTAMP, approved_by STRING)
        USING iceberg PARTITIONED BY (partner)""")
    return PartnerFileLoader(spark, tables, FeedContract(key_columns=("settlement_id",)))


def a_file(spark, *amounts, version=1, part=1, of=1, delivery=DELIVERY):
    """A file part and its rows. Settlement ids are unique per part."""
    rows = [(f"S{part}-{i}", amount, delivery.posting_date) for i, amount in enumerate(amounts)]
    frame = spark.createDataFrame(
        rows, "settlement_id STRING, amount_paise BIGINT, posting_date DATE"
    )
    file_id = f"{delivery.feed}-{delivery.posting_date}-v{version}-p{part}"
    file_part = FilePart(
        file_id=file_id,
        file_hash=f"sha-{file_id}",
        delivery=delivery,
        sequence_number=version,
        part_number=part,
        part_count=of,
        trailer_row_count=len(amounts),
        trailer_amount_paise=sum(amounts),
    )
    return file_part, frame


def current_total(loader) -> tuple[int, int]:
    row = (
        loader.current_rows()
        .selectExpr("count(1) AS n", "coalesce(sum(amount_paise), 0) AS total")
        .first()
    )
    return row["n"], row["total"]


def test_a_truncated_file_whose_trailer_matches_is_held_for_approval(spark, loader):
    for weeks_ago in (1, 2):
        earlier = Delivery("acme", "settlement", MONDAY - timedelta(weeks=weeks_ago))
        loader.receive(*a_file(spark, *[100] * 10, delivery=earlier))
        assert loader.publish(earlier, 1) is PublishResult.PUBLISHED
    before = current_total(loader)

    truncated = a_file(spark, *[100] * 4)  # four rows on a usual Monday of ten; trailer agrees
    assert loader.receive(*truncated) is PartState.STAGED

    assert loader.publish(DELIVERY, 1) is PublishResult.HELD_FOR_APPROVAL
    assert current_total(loader) == before, "nothing of the suspect file is visible"
    assert loader.publish(DELIVERY, 1, approved_by="ops-lead") is PublishResult.PUBLISHED


@pytest.mark.parametrize("arrival_order", [(1, 2), (2, 1)], ids=["in order", "older last"])
def test_an_older_version_arriving_late_never_becomes_current(spark, loader, arrival_order):
    files = {1: a_file(spark, 100, 200, version=1), 2: a_file(spark, 150, 200, version=2)}

    for version in arrival_order:
        loader.receive(*files[version])
        loader.publish(DELIVERY, version)

    assert current_total(loader) == (2, 350), "version 2 is current whatever the arrival order"


def test_a_version_in_parts_publishes_only_when_every_part_has_arrived(spark, loader):
    loader.receive(*a_file(spark, 100, 100, version=1))
    loader.publish(DELIVERY, 1)

    loader.receive(*a_file(spark, 50, version=2, part=1, of=3))
    loader.receive(*a_file(spark, 60, version=2, part=2, of=3))
    assert loader.publish(DELIVERY, 2) is PublishResult.INCOMPLETE
    assert current_total(loader) == (2, 200), "version 1 stays current, unmixed"

    loader.receive(*a_file(spark, 70, version=2, part=3, of=3))
    assert loader.publish(DELIVERY, 2) is PublishResult.PUBLISHED
    assert current_total(loader) == (3, 180), (
        "exactly version 2's three parts, nothing of version 1"
    )


def test_a_correction_replaces_the_previous_version_and_history_keeps_both(spark, loader):
    sunday = Delivery("acme", "settlement", MONDAY - timedelta(days=1))
    loader.receive(*a_file(spark, 1_000, delivery=sunday))
    loader.publish(sunday, 1)
    loader.receive(*a_file(spark, 100, 200, version=1))
    loader.publish(DELIVERY, 1)
    before_correction = datetime.now(UTC)

    loader.receive(*a_file(spark, 100, 250, version=2))
    loader.publish(DELIVERY, 2)

    assert current_total(loader) == (3, 1_350), "Monday corrected; Sunday's delivery untouched"
    as_known_then = (
        loader.rows_as_known_at(before_correction).agg({"amount_paise": "sum"}).first()[0]
    )
    assert as_known_then == 1_300


def test_a_rerun_after_a_crash_does_not_load_the_rows_twice(spark, loader):
    part, rows = a_file(spark, 100, 200)
    loader.load(part, rows)  # the loader loaded the rows, then crashed before recording it

    assert loader.receive(part, rows) is PartState.STAGED  # the rerun
    loader.publish(DELIVERY, 1)

    assert current_total(loader) == (2, 300)


def test_two_workers_publishing_the_same_version_at_once_make_one_current_version(spark, loader):
    loader.receive(*a_file(spark, 100, 200))
    errors: list[Exception] = []

    def publish():
        try:
            loader.publish(DELIVERY, 1)
        except Exception as error:
            errors.append(error)

    workers = [threading.Thread(target=publish) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert not errors, errors
    pointer = spark.table(loader.tables.pointer).where("valid_to IS NULL")
    assert pointer.count() == 1
    assert current_total(loader) == (2, 300)


def test_two_workers_receiving_the_same_part_at_once_load_it_once(spark, loader):
    part, rows = a_file(spark, 100, 200)
    errors: list[Exception] = []

    def receive():
        try:
            loader.receive(part, rows)
        except Exception as error:
            errors.append(error)

    workers = [threading.Thread(target=receive) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert not errors, errors
    assert spark.table(loader.tables.rows).count() == 2, "the part's rows were loaded twice"


@pytest.mark.parametrize("partner", ["acme'; DROP TABLE x; --", "acme settlement", ""])
def test_a_partner_identifier_that_could_change_the_sql_is_refused(partner):
    with pytest.raises(ValueError, match="characters outside"):
        Delivery(partner, "settlement", MONDAY)


def test_a_file_that_does_not_match_its_trailer_is_rejected_and_writes_nothing(spark, loader):
    part, rows = a_file(spark, 100, 200)
    wrong_trailer = FilePart(**{**part.__dict__, "trailer_amount_paise": 999})

    assert loader.receive(wrong_trailer, rows) is PartState.REJECTED
    assert spark.table(loader.tables.rows).count() == 0
