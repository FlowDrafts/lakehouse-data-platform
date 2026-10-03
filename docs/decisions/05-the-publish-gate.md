# ADR-05: Build gold on a temporary branch, check it, then publish or hold

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-03 |
| **Decision-makers** | Gaurav |
| **Related** | [Design doc](../architecture/lakehouse-design.md) §7.3, §10.2 · [ADR-01](01-catalog-and-consistency.md) · [Runbook](../runbooks/publish-gate-held.md) |

## Context and Problem Statement

A reader of a gold table needs to know it is correct and complete before they can see it. Two
things make that hard: the source keeps changing while we compare against it, and each table's
inputs arrive at different times. Where and how should gold be checked?

## Decision Drivers

- No unchecked gold version may ever be readable.
- Zero tolerance on money.
- A late input should hold only the tables that depend on it.
- Results should come in a standard format an auditor can read.

## Considered Options

| Option | Pros | Cons |
|---|---|---|
| Publish, then check | Simple | Wrong data is visible before anyone checks it |
| Check only at bronze | Catches problems early | Too early: completeness and tie-out need the downstream tables to exist |
| Hand-written comparison in Spark | Full control | Bespoke code with no standard report |
| **Temporary branch, a Great Expectations or Soda checkpoint, then publish or hold** | No unchecked gold version is ever readable; checks report in a standard format | A late input holds its dependent tables |

## Decision Outcome

Chosen option: **build on a temporary branch, check with a Great Expectations or Soda checkpoint,
then publish or hold**, because it's the only option where no unchecked gold version is ever
readable.

**Build.** Spark rebuilds gold for the affected date window on a temporary audit branch. The whole
window is replaced, so a date that now has no rows becomes empty instead of keeping the last run's
rows.

**Check.** The checkpoint reads the branch through Spark (`<table>.branch_<name>`). For each
business line and date it checks two things:
1. **Complete.** Every input this table declares has arrived for the window. Files arrive by
   their arrival calendar; change streams arrive once they have been read past the day's cut-off.
   Completeness is checked per table, against that table's own declared inputs.
2. **Correct.** Four values must equal the other side exactly, with zero tolerance:
   - the row count;
   - the signed paise total;
   - the number of distinct keys;
   - a content fingerprint: a hash of each row's key and amount, summed. It catches money moved
     between customers, which counts and totals miss. It's computed with the same hash and
     truncation in Postgres and in Spark.

   A row present on only one side is a failure.

**Against what.** Gold publishes about every 15 minutes while the source keeps moving:
- **Intraday**, gold is compared with silver, at the silver version it was built from.
- **Once a business date closes**, it is also compared with the source's own control totals, and
  the date is marked reconciled.

The version label states which of the two applies.

**Publish.** On a pass, `fast_forward` moves main to the branch in one atomic step. It refuses if
main has moved since the branch was cut, which catches a second writer. The version label is
stamped on the commit ([ADR-01](01-catalog-and-consistency.md)), and the results go to
OpenMetadata.

**Hold.** On a fail:
- main is untouched, and the previous version keeps serving, labelled with its age;
- on-call is paged;
- the branch is kept for 14 days for investigation, and never resumed: a retry always builds a
  fresh branch;
- a second alert fires if a hold stays open for more than 24 hours.

### Consequences

- Sources must report daily control totals. Without them only the silver comparison remains, and
  that can't detect data that never arrived.
- A late input holds every table that depends on it.
- A held branch stops its snapshots from being cleaned up until it expires.
- The framework runs and reports the checks, but the money logic inside them is ours.

### Confirmation

Tests 2.1–2.11 in the [test plan](../../tests/README.md).

## More Information

Revisit when gold must be fresher than about 15 minutes. At that point the build-check-publish
cycle itself becomes the bottleneck.
