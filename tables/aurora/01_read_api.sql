-- Aurora PostgreSQL sample: derived data served to apps through the Read API (ADR-06).
-- Money never comes from here; apps read it live from the owning service.

CREATE TABLE IF NOT EXISTS serving.customer_txn_history (
  customer_id     text        NOT NULL,
  txn_id          text        NOT NULL,
  txn_ts          timestamptz NOT NULL,
  business_line   text        NOT NULL,
  amount_paise    bigint      NOT NULL,     -- integer paise
  status          text        NOT NULL,
  version_label   text        NOT NULL,     -- returned with every response
  PRIMARY KEY (customer_id, txn_ts, txn_id)
);

-- A new version is loaded into serving.customer_txn_history_staging, then swapped in whole.
-- The rename takes a brief exclusive lock, so it waits at most 2 seconds and is retried:
--   BEGIN;
--   SET LOCAL lock_timeout = '2s';
--   ALTER TABLE serving.customer_txn_history RENAME TO customer_txn_history_old;
--   ALTER TABLE serving.customer_txn_history_staging RENAME TO customer_txn_history;
--   COMMIT;
--   DROP TABLE serving.customer_txn_history_old;
