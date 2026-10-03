# ADR-02: Tokenise personal data before anything stores it, using vault-issued tokens

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-03 |
| **Decision-makers** | Gaurav |
| **Related** | [Design doc](../architecture/lakehouse-design.md) §8 · [ADR-08](08-the-fast-path.md) · [ADR-09](09-one-time-migration.md) |

## Context and Problem Statement

The platform holds phone numbers, emails, PAN, Aadhaar references, names, addresses and device IDs
for 50M customers. The DPDP Act 2023 gives a right to erasure, lending and insurance carry
record-keeping duties, and data must stay in India. Bronze is append-only and kept for five years.
Where should personal data become a token, and what kind of token should it be?

## Decision Drivers

- No retained layer (Kafka, bronze, silver, gold) may hold a clear value.
- Erasure must be real, while records under a legal hold are still kept.
- Joins across products, and watchlist matching, must still work on tokens.
- Ingestion runs at 10k events/s.

## Considered Options

**Where to tokenise**

| Option | Pros | Cons |
|---|---|---|
| On the way into silver | Simple | Clear values sit in bronze for five years, so erasure would be false |
| Between Kafka and bronze | Fixes bronze | Kafka holds clear values for 7 days |
| **In the Debezium transform chain before the message is produced, and in the File Loader as it reads a file** | Nothing retained holds a clear value, Kafka included | Tokenisation sits on the critical ingestion path |

**What kind of token**

| Option | Pros | Cons |
|---|---|---|
| HMAC with a global key | Fast; computed locally | Erasure isn't real: anyone with the key can compute the token for every valid phone number and match them back |
| Format-preserving encryption | Keeps the value's shape | Reversible with the key, so it has the same weakness |
| **Vault-issued random token** | The token has no relationship to the value; delete the vault entry and the token means nothing | Every new value needs a vault lookup |

## Decision Outcome

Chosen option: **tokenise in the Debezium transform chain and in the File Loader, using
vault-issued random tokens**, because it's the only combination where no retained layer holds a
clear value and erasure is real.

- The same value always gets the same token, by lookup, so joins and watchlist matching still work.
- Real values exist only in the vault. Each customer's values are encrypted under that customer's
  own data key, which is wrapped by a KMS master key.
- A real value is returned only through the vault, for a stated purpose, and every request is
  logged. The fast path's case resolution is the main user ([ADR-08](08-the-fast-path.md)).
- **Erasure follows the retention class** declared for each personal field in its contract:
  - *No legal hold:* the customer's data key and vault entries are deleted at once.
  - *Under a retention obligation* (loan and policy records, KYC, fraud and anti-money-laundering
    watchlists): the entry is marked erasure-pending, masked on every read outside regulatory use,
    and deleted by a scheduled job when the retention period ends.
  - Backups of the vault's key store expire within a stated erasure window. Erasure is complete
    once the last backup holding the customer's key ages out.
  - Compliance sets the retention periods. The platform enforces them and logs every decision.

**Guardrails**

- **Fail closed.** If the vault is unreachable, the connector stops. It never passes clear text
  through and never skips a record (`errors.tolerance=none`).
- Tokenise the **before** image as well as the after image of every change, and the message key if
  it contains a personal field.
- **Classify every column.** A text column the contract doesn't classify is refused.
- Normalise before tokenising: phone numbers to `+91…`, emails lowercased, PAN uppercased.
- Never log record contents (`errors.log.include.messages=false`).
- Debezium's snapshot goes through the same chain as live changes.

### Consequences

- **The vault is on the critical path at 10k events/s.** A local cache of recent value-to-token
  lookups absorbs repeat customers. Its throughput is assumed, not measured.
- **A vault outage stops ingestion, by design.** Postgres then keeps WAL for the stalled
  replication slot, up to `max_slot_wal_keep_size`. Past that limit the slot is invalidated, which
  forces a re-snapshot ([ADR-03](03-database-changes-into-the-lake.md)).
- Raw partner files stay encrypted in the landing zone for 14 days. Apart from the source systems
  and the vault, these are the only clear values anywhere.

### Confirmation

Not yet in the test plan:
- a seeded canary personal value must never appear in clear in Kafka or bronze;
- a CI check fails if any contract column is left unclassified.

## More Information

Revisit when the vault can't sustain peak load even with caching. The fallback is HMAC with the key
held only in an HSM, accepting that erasure then depends on that key never leaking.
