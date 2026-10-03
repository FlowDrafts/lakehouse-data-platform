-- Control tables: the file register, the current-version pointer, and source control totals.

-- One row per received file part (ADR-04). A part already received, by its bytes or by its
-- place in a version, stops here as a duplicate.
CREATE TABLE IF NOT EXISTS glue.control.file_register (
  file_id           STRING    NOT NULL,
  file_hash         STRING    NOT NULL,
  partner           STRING    NOT NULL,
  feed              STRING    NOT NULL,
  posting_date      DATE      NOT NULL,
  sequence_number   BIGINT    NOT NULL,   -- the version; parts of one version share it
  part_number       INT       NOT NULL,
  part_count        INT       NOT NULL,   -- the manifest: a version publishes once all parts are in
  row_count         BIGINT    NOT NULL,   -- from the trailer; used by the truncation guard
  amount_paise      BIGINT    NOT NULL,
  state             STRING    NOT NULL,   -- STAGED | REJECTED | DUPLICATE | PUBLISHED | SUPERSEDED
  reason            STRING,               -- why it was rejected or held
  registered_at     TIMESTAMP NOT NULL
)
USING iceberg
PARTITIONED BY (partner);

-- Which version is current for each delivery. A flip is a compare-and-set that succeeds only for
-- a higher sequence number. Every flip is kept, which gives five years of "as known at".
-- Partitioned by partner, so only publishes for the same partner contend.
CREATE TABLE IF NOT EXISTS glue.control.file_pointer (
  partner           STRING    NOT NULL,
  feed              STRING    NOT NULL,
  posting_date      DATE      NOT NULL,
  sequence_number   BIGINT    NOT NULL,
  valid_from        TIMESTAMP NOT NULL,
  valid_to          TIMESTAMP,            -- NULL while current
  approved_by       STRING                -- set only when a held version is approved
)
USING iceberg
PARTITIONED BY (partner);

-- Each source's own totals for a closed business date. The gate reconciles against these
-- once a date closes (ADR-05).
CREATE TABLE IF NOT EXISTS glue.control.source_control_totals (
  source            STRING    NOT NULL,
  business_line     STRING    NOT NULL,
  business_date     DATE      NOT NULL,
  row_count         BIGINT    NOT NULL,
  amount_paise      BIGINT    NOT NULL,
  distinct_keys     BIGINT    NOT NULL,
  fingerprint       BIGINT    NOT NULL,   -- same 32-bit hash per row as the lake side, summed
  reported_at       TIMESTAMP NOT NULL
)
USING iceberg
PARTITIONED BY (business_date);
