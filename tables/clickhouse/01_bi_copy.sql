-- ClickHouse sample: the BI copy of published gold, read by Cube (ADR-07).

CREATE TABLE IF NOT EXISTS gold.fact_transaction
(
  txn_id          String,
  customer_id     String,
  business_line   LowCardinality(String),
  amount_paise    Int64,                    -- integer paise, never Decimal or Float
  status          LowCardinality(String),
  business_date   Date
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(business_date)
ORDER BY (business_line, business_date, txn_id);

-- Which published version each copy holds. Cube's refresh key reads this, and the load writes
-- one row after every swap.
CREATE TABLE IF NOT EXISTS platform.loaded_versions
(
  table_name      String,
  snapshot_id     Int64,                    -- the Iceberg snapshot that was published
  version_label   String,                   -- the source positions it was built from
  loaded_at       DateTime
)
ENGINE = MergeTree
ORDER BY (table_name, loaded_at);

-- A load never writes to the live table. It fills a staging copy, then swaps both atomically:
--   CREATE TABLE gold.fact_transaction_staging AS gold.fact_transaction;
--   INSERT INTO gold.fact_transaction_staging SELECT ... ;   -- one published version
--   EXCHANGE TABLES gold.fact_transaction_staging AND gold.fact_transaction;
