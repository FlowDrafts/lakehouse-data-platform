# Specifications

The plans that drove the AI-assisted development of this repository, reproduced as they were
approved.

## How They Were Used

The repository was built with Claude Code in **plan mode**:
1. For each piece of work, the assistant first explored the repository and wrote a plan: the
   context, the changes, and how they would be verified.
2. The author reviewed the plan, sent it back with corrections where needed, and approved it.
3. Only then was it implemented, and verified as the plan said: tests on a real Iceberg engine,
   mutation testing, link and lint checks, and CI.

The architecture itself, the choice of hard problems, and the trade-offs were decided in
discussion before any of these plans; the plans turned those decisions into concrete work. Each
plan describes the repository *as it was at that moment*, so later plans supersede earlier ones,
and some file names they mention were changed afterwards.

## The Plans

| # | Plan | What it produced |
|---|---|---|
| 1 | [Design document structure](01-design-document-structure.md) | The technical design document's industry-standard structure |
| 2 | [Design document technical review](02-design-document-technical-review.md) | Corrections to technical claims, and tighter wording |
| 3 | [Architecture decision records](03-architecture-decision-records.md) | The decision log and the ADRs in MADR format |
| 4 | [Data contracts](04-data-contracts.md) | Sample contracts in the Open Data Contract Standard |
| 5 | [CI workflows](05-ci-workflows.md) | CI, release, Dependabot and code owners |
| 6 | [Hard problems and implementation](06-hard-problems-and-implementation.md) | The choice of the three hard problems from how the sources misbehave, and the code and tests for them |
| 7 | [Independent review](07-independent-review.md) | A review of the whole repository against the brief, and the fixes that followed |

Plans for routine housekeeping (renaming the project and publishing it) are not included.
