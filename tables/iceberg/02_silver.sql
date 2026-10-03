-- Silver samples: one current-state table from database changes, one versioned file table.

-- Current state, kept equal to the source by the ordered merge (ADR-03), advanced only to the
-- transaction cut (ADR-10). Bucketed on the merge key, so a merge rewrites only the buckets it
-- touches. Each cut is tagged cut_<source>_<position>, and gold reads every input at one cut.
CREATE TABLE IF NOT EXISTS glue.silver.loan (
  loan_id               STRING    NOT NULL,
  customer_id           STRING,
  customer_phone_token  STRING,                 -- a vault token, never the real value (ADR-02)
  principal_paise       BIGINT,
  status                STRING,
  loan_terms            STRING,                 -- never overwritten by Debezium's placeholder
  source_incarnation    INT       NOT NULL,     -- ordered first, then source_lsn
  source_lsn            BIGINT    NOT NULL,     -- a change applies only if strictly newer
  is_deleted            BOOLEAN   NOT NULL,     -- a delete clears the values and keeps the key
  updated_at            TIMESTAMP NOT NULL
)
USING iceberg
PARTITIONED BY (bucket(64, loan_id))
TBLPROPERTIES (
  'format-version'    = '2',
  'write.merge.mode'  = 'merge-on-read',
  'write.delete.mode' = 'merge-on-read',
  'write.update.mode' = 'merge-on-read'
);

-- Every row of every version of a partner delivery, appended and tagged with its version and
-- file (ADR-04). Never read directly: readers use the view silver.partner_settlement, which
-- keeps only the version the current-version pointer names (04_control.sql):
--   ... JOIN glue.control.file_pointer p USING (partner, feed, posting_date, sequence_number)
--   WHERE p.valid_to IS NULL
-- "As known at" a past moment T swaps that condition for valid_from <= T < valid_to.
CREATE TABLE IF NOT EXISTS glue.silver.partner_settlement_versions (
  partner               STRING    NOT NULL,
  feed                  STRING    NOT NULL,
  sequence_number       BIGINT    NOT NULL,     -- the version, as the partner numbers it
  file_id               STRING    NOT NULL,     -- the part it came from
  settlement_id         STRING    NOT NULL,
  amount_paise          BIGINT    NOT NULL,     -- signed: refunds are negative
  posting_date          DATE      NOT NULL,     -- adjustments to earlier dates post today
  utr                   STRING                  -- bank payment reference
)
USING iceberg
PARTITIONED BY (partner, posting_date)          -- loads for different deliveries never conflict
TBLPROPERTIES (
  'format-version' = '2',
  -- Exact per-file bounds on file_id (the default keeps 16 characters), so replacing one file's
  -- rows touches only that file's data files.
  'write.metadata.metrics.column.file_id' = 'full'
);
