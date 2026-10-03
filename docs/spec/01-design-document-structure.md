# Plan: restructure the design document to an industry-standard format

## Context

`docs/architecture/lakehouse-design.md` answers the brief's questions, but its headings follow
the brief's informal wording ("Getting data in", "Living with it", "Honesty") rather than a
standard technical design document. The user asked for three things:
1. Remove the "stack, and what each part buys" paragraph from the summary, and move that content
   into the architecture table as a **"What it buys"** column (already agreed).
2. Remove the "Reference material" paragraph at the bottom.
3. Restructure the whole document with industry-standard headings, **high-level design first,
   then detailed design**. That matches the user's earlier ask for functional and non-functional
   requirements and an HLD-then-LLD structure.

Hard constraints from the brief:
- The design doc is "roughly 4–6 pages". Today it's ~3,375 real words (~6.1 pages).
- It must still answer every question the brief asks.
- It must keep an explicit **honesty** section: what was left out, where I'm unsure, and AI vs own
  decisions.

This is a docs-only change. No code.

**Decisions confirmed with the user:**
- **Length:** the body stays at about 6 pages or less, with the glossary and sizing in appendices
  outside the page count.
- **Disclosure:** remove the "Reference material" paragraph entirely, with no replacement line.
  The user made this call after the concern was raised.
- **Author:** the document-control block gets a placeholder, `Author: <your name>`, for the user
  to fill in before submitting.

## Target structure

| # | Heading | Content source (moved, not duplicated) |
|---|---|---|
| — | **Document control** (table: Status "Draft for review", Version, Last updated, Author `<your name>`, Related documents) | Today's link line at the top |
| 1 | **Executive Summary** | Trimmed summary: what it is, the two rules, the three challenges, day-one migration. **"Stack buys" paragraph removed** |
| 2 | **Background and Problem Statement** | New, ~80 words, from the brief's context: three businesses, scattered data, nobody sure what's current or correct |
| 3 | **Goals and Non-Goals** | Goals: new bullets. Non-goals: moved from Honesty's "left out" list |
| 4 | **Requirements** — 4.1 Functional (FR-1…), 4.2 Non-Functional (table: scale, freshness, correctness, durability, availability, security and compliance, auditability, cost) | Freshness and scale rows move here from Assumptions |
| 5 | **Assumptions and Constraints** | The remaining assumption rows |
| 6 | **High-Level Design** — 6.1 Architecture Overview (diagram + four exits + fast path), 6.2 Data Layers (Medallion), 6.3 Technology Choices and Alternatives Considered (**adds a "What it buys" column**; links the ADRs) | Today's §1 bullets and §3 |
| 7 | **Detailed Design** — 7.1 Data Ingestion, 7.2 Initial Data Migration, 7.3 Data Quality, Freshness and Semantics, 7.4 Data Serving and Access, 7.5 Real-Time Fast Path (extension) | Today's §4, §5, §6, §7 |
| 8 | **Security, Privacy and Compliance** | The PII paragraph moves here from ingestion. Adds encryption, access grants and localisation lines. The erasure point moves here from Honesty |
| 9 | **Operational Considerations** — 9.1 Orchestration and Maintenance, 9.2 Monitoring and Alerting, 9.3 Failure Modes and Recovery, 9.4 Cost | Today's §8 |
| 10 | **Key Technical Challenges (Deep Dives)** — 10.1 Partner file ingestion, 10.2 Publishing only verified data, 10.3 One version of the truth across serving paths | Today's §9, tightened |
| 11 | **Testing Strategy** | Principle plus a pointer to `tests/test-plan.md`, and which tests get coded first |
| 12 | **Risks and Mitigations** (table: risk, impact, mitigation) | Today's "where it breaks first" |
| 13 | **Open Questions** | Schema registry; landing retention vs partner dispute window; app traffic measurement; vault throughput |
| 14 | **Honesty: Limitations, Uncertainties and AI Use** | Pointer to Non-goals, "where I'm unsure", "harder than anything solved here", code status, AI use. **"Reference material" removed** |
| A | **Appendix A: Glossary** (~8 terms) | New: bronze/silver/gold, gate, held branch, version label, outbox, tokenisation |
| B | **Appendix B: Sizing** | Rows/day, retention, Iceberg footprint, Kafka retention, partitions, files/day |

## Brief question → section (must all be covered)

| Brief asks | Section |
|---|---|
| Architecture and why: layers, table format, engines, catalog, storage; chose / rejected / cost | 6.2, 6.3 |
| Name the stack and what it buys | 6.3 ("What it buys" column) |
| Getting data in; when a source misbehaves | 7.1, 7.2 |
| Trustworthy: correct, current, means what they think | 7.3 |
| Serving: what each consumer gets | 7.4 |
| Living with it: day to day, failure, recovery, cost, where it breaks first | 9, 12 |
| 2–3 hard problems, deep | 10 |
| Test plan | 11 → `tests/test-plan.md` |
| Assumptions where the brief is ambiguous | 5 |
| Honesty: left out, unsure, AI vs own | 3 (non-goals), 14 |
| Architecture diagram | 6.1 → `lakehouse_architecture.drawio` |

## Page budget

Keep the **body (sections 1–14) at about 6 pages**, with the appendices on top. Content is
*moved*, not duplicated. To make room for the new sections:
- shorten the executive summary;
- shorten the ingestion table's cells;
- remove the "Tests" lines from the deep dives (section 11 maps them);
- drop the "Glue down" and "Flink down" recovery rows (they're covered in ADRs 01 and 08);
- tighten the cost and code-status paragraphs.

## Other edits

- Update every in-text cross-reference ("section 4", "section 8", "Section 6 depends on this") to
  the new numbering.
- The links to the ADRs, the test plan and the runbook stay the same. They're relative to
  `docs/architecture/`.
- No changes to the ADRs, the test plan or the runbook. None of them cite design-doc section
  numbers.

## Files

- **Modify:** `docs/architecture/lakehouse-design.md`. A full rewrite, using Write after reading
  the file.
- **Read only, for consistency:** `docs/decisions/00-decision-register.md`, ADRs 01–09,
  `tests/test-plan.md`.

## Verification

1. Link check: a script resolving every relative link in `docs/**/*.md` and
   `tests/test-plan.md` reports zero broken.
2. Word count, real words only: body about 6 pages at ~550 words/page.
3. `grep` confirms "Reference material" and the "stack, and what each part buys" paragraph are
   gone.
4. `grep` the heading list and check it against the target structure above.
5. Walk the "brief question → section" table and confirm each section exists and answers it.
6. No stale cross-references: `grep -n "section [0-9]"` matches the new numbering.
