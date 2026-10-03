-- Gold sample. Built on an audit branch and published only after the gate passes (ADR-05).
-- Its declared inputs and checks live in its contract (contracts/gold/fact_transaction.odcs.yaml),
-- and each publish stamps the version label on the commit as a snapshot property (ADR-01).
CREATE TABLE IF NOT EXISTS glue.gold.fact_transaction (
  txn_id          STRING    NOT NULL,
  customer_id     STRING    NOT NULL,
  business_line   STRING    NOT NULL,
  amount_paise    BIGINT    NOT NULL,     -- signed integer paise
  status          STRING    NOT NULL,
  business_date   DATE      NOT NULL
)
USING iceberg
PARTITIONED BY (days(business_date))   -- the gate replaces whole dates
TBLPROPERTIES ('format-version' = '2');
