-- Bronze samples: database changes as received, appended by the Iceberg sink connector (ADR-03).
-- One bronze table per source table, so the source is the table rather than a partition.
-- Append-only and partitioned by ingest hour only, so a record that can't be parsed still lands.

-- Each change, flattened by Debezium's ExtractNewRecordState transform.
CREATE TABLE IF NOT EXISTS glue.bronze.lending_loan_cdc (
  loan_id               STRING,
  customer_id           STRING,
  customer_phone_token  STRING,
  principal_paise       BIGINT,
  status                STRING,
  loan_terms            STRING,                 -- large JSON; Debezium's placeholder when unchanged
  op                    STRING    NOT NULL,     -- c | u | d | r (snapshot read) | t (truncate)
  source_table          STRING    NOT NULL,     -- routes each change to its bronze table
  source_incarnation    INT       NOT NULL,     -- added by the connector; bumped by a re-snapshot
  source_lsn            BIGINT    NOT NULL,     -- the change-log position
  transaction_id        STRING,                 -- NULL only for snapshot and export rows
  kafka_partition       INT       NOT NULL,
  kafka_offset          BIGINT    NOT NULL,
  ingest_ts             TIMESTAMP NOT NULL
)
USING iceberg
PARTITIONED BY (hours(ingest_ts))
TBLPROPERTIES ('format-version' = '2', 'write.parquet.compression-codec' = 'zstd');

-- Debezium's transaction records (ADR-10), from a single-partition topic, so `position` (the
-- Kafka offset) is commit order. Each END record says how many events the transaction produced
-- for each table; the transaction cut is computed from these.
CREATE TABLE IF NOT EXISTS glue.bronze.lending_transactions (
  position              BIGINT    NOT NULL,
  transaction_id        STRING    NOT NULL,
  status                STRING    NOT NULL,     -- BEGIN | END
  data_collections      ARRAY<STRUCT<data_collection: STRING, event_count: BIGINT>>,
  committed_at          TIMESTAMP NOT NULL,
  ingest_ts             TIMESTAMP NOT NULL
)
USING iceberg
PARTITIONED BY (hours(ingest_ts))
TBLPROPERTIES ('format-version' = '2');
