# Specification

What the platform must do, and how we know it does. Each user story has acceptance criteria;
each criterion maps to a test ID in the [test plan](../../tests/README.md). Status: ✅ built and
tested, 📐 designed (no code yet).

The *why* behind each story is in the [design document](../architecture/lakehouse-design.md) and
the [decision records](../decisions/00-decision-register.md). The rules every story must keep
are in the [constitution](constitution.md).

## Users

| User | Needs |
|---|---|
| Analysts and finance | Dashboards and chat answers they can trust to the paise |
| Applications | Fast reads of derived data, with money always live from its service |
| Data scientists | Point-in-time features with no leakage |
| Auditors | Any month-end figure reproduced exactly, traced to its source |
| On-call engineers | Failures that are safe by default and diagnosable |

## US-1 Partner File Versions ✅

*As finance, I want each partner delivery to have exactly one current, whole version, so that
corrections, resends and truncated files never change a number silently.*

| # | Acceptance criterion | Test |
|---|---|---|
| 1 | Given a file far smaller than the same weekday usually is, when it is published, then it is held until someone approves it | 1.1 |
| 2 | Given versions 1 and 2 of a delivery, in either arrival order, then version 2 is current | 1.2 |
| 3 | Given two of a version's three parts, then the previous version stays current, unmixed | 1.3 |
| 4 | Given a correction, then it is current, and "as known at" before it returns the old rows; other deliveries are untouched | 1.4 |
| 5 | Given a crash or two racing workers, then a part's rows load exactly once | 1.5, 1.8 |
| 6 | Given two workers publishing the same version at once, then there is one current version | 1.6 |
| 7 | Given a file that doesn't match its trailer, then nothing is loaded | 1.7 |
| 8 | Given a partner name that could alter SQL, then it is refused | 1.9 |
| 9 | 📐 Given a file missing when its arrival window closes, then every dependent gold table is held | 1.10 |
| 10 | 📐 Given a change-only feed missing a sequence number, then the feed stops at the gap | 1.11 |
| 11 | 📐 Given a reference file, then its "updated" event is sent only after its version is current | 1.12 |

## US-2 Publishing Only Verified Gold ✅

*As an analyst, I want gold to be readable only when it is complete and ties to the source
exactly, so that a wrong number is never shown, only a late one.*

| # | Acceptance criterion | Test |
|---|---|---|
| 1 | Given money moved between two customers (counts and totals unchanged), then the build is held | 2.1 |
| 2 | Given a declared input that isn't complete, then the table is held and readers keep the previous version | 2.2 |
| 3 | Given a clean build, then it is published with its version label on the commit | 2.3 |
| 4 | Given silver that moved after the build read it, then the comparison uses the silver the build read | 2.4 |
| 5 | Given a date that now has no rows, then it becomes empty | 2.5 |
| 6 | Given a day only the build has, then it is a break | 2.6 |
| 7 | Given main moved since the branch was cut, then publishing is refused | 2.7 |
| 8 | The fingerprint is identical in Spark and in the source database's form | 2.8 |
| 9 | 📐 A paise sum that overflows fails the query | 2.9 |
| 10 | 📐 Readers during a publish see version N or N+1, never part of each | 2.10 |
| 11 | 📐 An intraday version is labelled "checked against silver", not "reconciled" | 2.11 |

## US-3 A Consistent Cut Across One Database ✅

*As an analyst, I want gold to read every table of a source at the same point, so that I never
see a loan without its ledger lines.*

| # | Acceptance criterion | Test |
|---|---|---|
| 1 | Given a transaction with events still in flight on any table, then it is not in the cut | 3.1 |
| 2 | Given an incomplete transaction followed by complete ones, then the cut stops before it | 3.2 |
| 3 | A date is complete only once the cut passes its cut-off; a heartbeat counts | 3.3 |
| 4 | Reading every table at one cut never shows a torn transaction; each new cut reads only what is new | 3.4 |
| 5 | Rerunning a cut after a failure completes with the same result | 3.5 |

## US-4 Database Changes Merged in Source Order ✅

*As the platform, I want silver to equal the source however changes arrive.* Acceptance
criteria C.1–C.6: older changes never overwrite newer ones; deletes win and stay deleted; a
truncate fails the batch; a new incarnation outranks older positions; an unchanged large column
keeps its value.

## US-5 Serving Consistency 📐

*As an application, I want every answer to come from one whole, labelled version.* Acceptance
criteria S.1–S.6: copies swap in whole versions; the Read API pins versions and never mixes them;
every response carries a version and freshness, and fast-path answers carry `verified: false`;
a lagging copy shows its gap; ClickHouse loads only published versions; money screens never use
the Read API.

## US-6 One-Time Migration 📐

*As the platform, I want existing history loaded once, with no gap and no double count.*
Acceptance criteria M.1–M.3.

## US-7 Third-Party API Extraction 📐

*As the platform, I want API pulls that never lose a record.* Acceptance criteria:
- the raw response is saved before it is parsed;
- pages are read by key, never by offset;
- each pull re-reads a lookback window and deduplicates, so a record that appears late is still
  caught;
- a periodic full sweep is the source's completeness signal.

## Non-Functional Requirements

From the [design document](../architecture/lakehouse-design.md) §4.2:
- **Scale:** 10k events/s peak, 500M file rows/day, 50M customers, five years kept.
- **Freshness:** bronze ≤2 min, silver ≤7 min, gold ≤20 min.
- **Correctness:** zero tolerance.
- **Compliance:** RBI, IRDAI, DPDP 2023, with all data in India.
- **Auditability:** any month-end figure reproducible exactly.

## Out of Scope

Restatement of closed periods, matching transactions across sources, source purges, ML training,
and cross-region recovery (see design §3 and §14).
