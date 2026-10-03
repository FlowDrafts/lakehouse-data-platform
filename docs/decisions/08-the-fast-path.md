# ADR-08: A Flink fast path limited to complete facts, always labelled unverified

| | |
|---|---|
| **Status** | Accepted (an extension beyond the brief) |
| **Date** | 2026-10-03 |
| **Decision-makers** | Gaurav |
| **Related** | [Design doc](../architecture/lakehouse-design.md) §7.5 · [ADR-02](02-personal-data-tokenisation.md) · [ADR-04](04-partner-and-ops-files.md) · [ADR-06](06-application-reads.md) |

## Context and Problem Statement

Gold is about 20 minutes behind. Fraud scoring, risk flags and watchlist checks can't wait that
long. The brief doesn't ask for real time, so this is a deliberate second lane: the speed layer of
a Lambda architecture, not a standard part of a lakehouse. What may this lane read, and what may
apps do with its output?

## Decision Drivers

- Decisions in seconds, for the few use cases that need them.
- Never act on half a transaction.
- Every signal can be traced and replayed.
- Unverified output must never pass for verified.

## Considered Options

| Option | Pros | Cons |
|---|---|---|
| No fast path | Simplest; nothing unverified reaches an app | No answer for decisions that can't wait 20 minutes |
| Flink on every Kafka topic | Sees everything | Change topics carry pieces of transactions. A loan and its ledger line can arrive apart, so Flink can score half a transaction |
| Files through Flink | One lane for everything urgent | Duplicates the file checks in a second engine; the reference fast track covers this instead ([ADR-04](04-partner-and-ops-files.md)) |
| **Flink on event, outbox and reference-update topics only, with every signal labelled unverified** | Fast, and every input is a complete fact | A second processing engine, with nothing verifying its output |

## Decision Outcome

Chosen option: **Flink on event, outbox and reference-update topics only, with every signal
labelled unverified**, because it gives decisions in seconds without ever reading a partial
transaction.

**What Flink reads**
- App events, outbox events and reference updates. Never raw database change topics.
- **Outbox pattern.** A service writes one `loan_disbursed` row to an outbox table, in the same
  transaction as the loan and ledger rows. Debezium delivers that row as one complete fact.
- Reference data is held in memory, and refreshed on each "reference updated" event.

**How it delivers**
- Flink checkpoints, with an exactly-once Kafka sink (a transactional producer). Consumers read
  with `isolation.level=read_committed`, and events are deduplicated on `event_id`.
- Output goes to a fast-path Kafka topic that apps subscribe to. A slow or failed app never holds
  Flink back, and apps can replay the topic.

**How signals are labelled and audited**
- Every signal is labelled `source: fast_signal, verified: false`, with the Kafka positions it was
  computed from.
- The topic is also appended to bronze, so every signal ever sent is recorded, with time travel.
- Flagged cases go to case resolution: the real value comes from the vault, scoped to one record,
  and every access is audited. A score never triggers an irreversible action (blocking, reversing,
  holding funds) without that step.

**How it is operated**
- Each use case states what happens when Flink is down: allow without a score, or hold.
- A daily job compares signals with what gold later shows, to measure drift.

### Consequences

1. No verification: a scoring bug reaches the app directly.
2. Live and reconciled numbers can disagree until gold catches up.
3. A second engine computes features similar to Spark's. A model trained on gold and scored on
   Flink sees inputs in production that it never saw in training.
4. Apps that rely on signals depend on Flink being up.
5. Consistent tokens leak frequency patterns, though not values.
6. The outbox requires source teams to change their code.

### Confirmation

- Test S.3 in the [test plan](../../tests/README.md): every fast-path answer carries
  `verified: false`.
- The daily drift job is not yet in the test plan.

## More Information

Revisit if no use case needs a decision faster than gold can give. In that case, remove the lane.
