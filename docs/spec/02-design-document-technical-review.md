# Plan: technical review and tightening of the design document

## Context

The user asked for a technical review of `docs/architecture/lakehouse-design.md`. The goal is to
remove anything **redundant** (the same fact stated in several sections) or **over-expressive**
(rhetoric or claims with no technical justification), and to share the findings before editing.

The review found:
- 12 redundancies or over-expressions to remove;
- 6 technical inaccuracies, where a statement is broader than what the design actually guarantees;
- 7 rhetorical phrases to make precise.

The document is currently about 3,400 words, roughly 6.2 pages. These changes should bring it to
about 3,100 words, under 6 pages, without losing any section or technical content.

This is a docs-only change: only the design doc is edited.

## A. Technical inaccuracies (fix: claims broader than the design guarantees)

| # | Where | Problem | Fix |
|---|---|---|---|
| T1 | §1, rule 1 | "Nothing becomes readable until it is proven correct and complete." Not true: bronze and silver are readable (data scientists read silver), and fast-path signals are explicitly unverified | "No **gold** table becomes readable until it is proven correct and complete" |
| T2 | §1, rule 2, and §10.3 Guarantee | "Every answer states its version…". Money is read live from the owning service, and those answers carry no version label | "Every answer **served from the lake or the fast path** states its version, freshness and verification status" |
| T3 | §3 Goals | "rebuildable from the sources". Kafka keeps only 7 days, and the sources don't keep history. Bronze is the replay point | "rebuildable from bronze" |
| T4 | §6.3 Storage row | "~200 files a day" and ">200,000 files a day" read as platform totals. Both are per events table (Appendix B) | Add "per events table" |
| T5 | Appendix B | "Files per day" doesn't say what it's per | "Files per day (one events table)" |
| T6 | §7.3 Completeness | Change streams count as arrived "by having read past the day's cut-off". An **idle** source never produces a change past the cut-off, so its dependent gold would be held forever | Add: "Debezium heartbeats keep idle sources advancing past the cut-off". This is the one small addition, closing a real gap |

## B. Redundancy (remove: the fact stays where it belongs)

| # | Remove from | Duplicates | Stays in |
|---|---|---|---|
| R1 | §2, last sentence ("every table is either proven correct… or not visible at all") | Rule 1, and also overstated (T1) | §1 |
| R2 | §3 Goals, the "traced back to source for five years" bullet | FR-7 and NFR Auditability | §4 |
| R3 | §3 Non-goals, the validator history ("It was removed because…") | §7.3 Limit, §14 code status | Shortened to "Blocking unsafe ad hoc queries at query time (§7.3)" |
| R4 | §6.1, the empty zone bullets "Sources." and "Consumers.", and "gold only becomes visible after the gate" | §6.2 Gold row, §10.2 | §6.1 becomes one short paragraph |
| R5 | §7.3 Correctness: the list of checks (counts, paise, keys, fingerprint, zero tolerance, publish or hold) | §10.2 Design | One line: "enforced by the publish gate (§10.2)" |
| R6 | §7.3, "A held table keeps serving its last good version, labelled" | NFR Availability, §9.3, §10.2 Guarantee | §4.2, §10.2 |
| R7 | §8, the Localisation bullet | NFR Compliance, Assumptions (Platform) | §4.2, §5 |
| R8 | §9.1, "Held branches expire after 14 days" | §10.2 step 4, Glossary | §10.2 |
| R9 | §9.3, the "Bad partner file" row | §7.1 Partner files row, the runbook | §7.1 and runbook |
| R10 | §9.4, "A smaller stack was estimated at about $10k a month; this one is a multiple of that" | Refers to an earlier design the reader never sees; unsupported | Removed. Keep "order of magnitude, not modelled", the cost ranking, and the month-end tag point |
| R11 | §14 Unsure: "merge throughput at peak" and "the cost figure" | Risk 1 (unmeasured) and §9.4 (not modelled) | §12, §9.4 |
| R12 | §11, "A crash gets fixed the same day; a wrong total ends up in a board pack." | Rhetoric restating the line before it | Removed |

## C. Over-expressive phrasing (make precise; the meaning is kept)

| Where | Now | Becomes |
|---|---|---|
| §3 Goals | "erasure actually works" | "enforceable erasure" |
| §6.2 Bronze | "a dropped record can't be recovered, an ugly one can" | "unparseable rows land flagged for reprocessing; nothing is dropped" |
| §10.2 Why | "a check that passes on half the data is worse than none" | "a check run on incomplete data reports a false pass" |
| §10.3 Why | "a number with no context, which looks exactly like a right one" | "a stale or unverified number served without its label is indistinguishable from a verified one" |
| §11 | "Every guard is deleted on purpose…" | Named precisely: "mutation testing: each guard is removed in turn, and the suite must fail" |
| §12 Risk 2 | "Stale dashboards for teams that did nothing wrong" | "Dependent tables go stale" |
| §12 Risk 5 | "The hardest unsolved problem here" | "Not automated (non-goal, §3)" |

## Kept deliberately (looks repetitive, but each instance has a job)

- The serving engines appear in §1, §6.1, §6.3 and §7.4. These are summary, overview, decision
  and per-consumer detail respectively.
- The fast-path label appears in §7.4, §7.5 and the Glossary. These are the consumer view, the
  design, and the definition.
- §7.1's partner-file row and §10.1. The first is a summary, the second the deep dive.
- The Glossary repeats terms from the body. That's what a glossary does.

## Files

- **Modify:** `docs/architecture/lakehouse-design.md`, with targeted edits only, no rewrite.
- No other files change. The ADRs, test plan and runbook are already consistent with these fixes.
  T6's heartbeat point is consistent with ADR 03.

## Verification

1. A script check: every relative link in `docs/**/*.md` and `tests/test-plan.md` resolves.
2. Every "section N", "§N" and "risk N" cross-reference points at something that exists.
3. `grep` confirms each removed phrase is gone: "board pack", "did nothing wrong", "$10k",
   "actually works", "ugly one", "worse than none", "Sources.", "Localisation".
4. The body word count, real words only, is about 3,100, under 6 pages.
5. Re-read §1, §7.3 and §10.3 to confirm the rules and guarantees now match the design exactly
   (T1, T2).
