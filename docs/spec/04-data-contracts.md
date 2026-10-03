# Plan: `contracts/` as sample data contracts in the industry-standard format, with a README

## Context

The user asked what `contracts/` holds and why it's needed. The current design depends on it in
four places:
- **ADR-04:** the File Loader reads each feed's contract.
- **ADR-02:** tokenisation reads each column's classification and each personal field's retention
  class.
- **ADR-05:** the gate reads each gold table's declared inputs.
- **Risk 3:** the CI contract check catches enum drift.

Today the folder holds a home-grown YAML format written for the earlier design. Several fields
contradict the ADRs (partner versions ordered by timestamp, a reconciliation method that no
longer exists, the word "quarantined"). It also holds a metrics file that belongs to the semantic
validator, which is being removed.

**The user's direction:**
- Use the industry standard.
- Keep it light. The files are samples that show what a contract holds; don't go deep or add many
  technicalities.
- Add a README local to the folder.

**The standard:** the Open Data Contract Standard (ODCS), Bitol project, Linux Foundation. The
latest release is **v3.2.0** (Sep 2026). Syntax was checked against the spec: `apiVersion`, `kind`,
`id` and `version` are required; then `schema` → `properties`; `quality` (`metric`,
`mustBe`/`mustBeGreaterThan`, `arguments.validValues`, or `type: text`); `slaProperties`
(`property`/`value`/`unit`); `team`; `customProperties`.

## New layout

```
contracts/
├── README.md
├── sources/
│   ├── lending.loan.odcs.yaml        replaces lending.loan.yml
│   └── partner.acme.odcs.yaml        replaces partner.acme.yml
└── gold/
    └── fact_transaction.odcs.yaml    replaces marts/gold.fact_transaction.yml
```

**Removed:**
- `metrics/transactions.yml`. Metric definitions aren't data contracts; Cube's data model holds
  them (ADR-07).
- `enums.yml`. Allowed values move onto the column itself, as the standard
  `invalidValues` / `validValues` rule.

## Each sample: about 40–50 lines, with a short comment where a field needs one

**Common to all three:**
- the fundamentals: `apiVersion: v3.2.0`, `kind`, `id`, `name`, `version: 1.0.0`,
  `status: active`, `domain`, and `description` (purpose and usage);
- `schema` with 4–6 key columns. Every column has a `classification`, and personal columns are
  `restricted` (ADR-02: classify every column);
- `team` as the owner;
- `slaProperties` for latency, frequency and retention.

**`sources/lending.loan.odcs.yaml`** (a database table captured by CDC):
- `loan_id` is the primary key; `principal_paise` is a `bigint`;
- `customer_phone` is `restricted`, with `retentionClass: loan_record` as a custom property;
- `status` lists its valid values (the old enum list);
- silver latency 7 min; retention 5 y;
- `customProperties`: `ingestion: cdc`, `orderingKey: source_lsn`, `controlTotals: daily`.

**`sources/partner.acme.odcs.yaml`** (a partner settlement file):
- `settlement_id` is the primary key, with `duplicateValues` `mustBe: 0`;
- `business_date`, `amount_paise` and `utr` as columns;
- frequency 1 d; retention 5 y;
- `customProperties`, each matching ADR-04 §2:
  - `deliveryMode: full_snapshot`;
  - `versionOrder: sequence_number`;
  - `businessDayCutoff` and `arrivalWindow`, with the Asia/Kolkata timezone;
  - `trailer: [row_count, amount_paise_total, file_hash]`;
  - `truncationThreshold`;
  - `reference: false`;
  - `optional: false`.

**`gold/fact_transaction.odcs.yaml`** (a gold table):
- `txn_id` is the primary key; `customer_id` is a `restricted` token; `status` lists its valid
  values;
- table-level `quality` of `type: text` stating the gate's four zero-tolerance checks (ADR-05);
- latency 20 min; retention 5 y;
- `customProperties`: `inputs` (the declared inputs used for completeness), `rebuildWindowDays: 2`,
  `monthEndTag: true`.

## `contracts/README.md` (about one page)

- **What a data contract is.** One line, plus the ODCS link, and the statement that these are
  samples (one of each kind), not a complete set.
- **Scope line.** A full set of contracts, and validating them in CI, are out of scope for this
  design.
- **Why the platform needs them.** A table of: who reads the contract, what it takes from it, and
  the ADR. That covers the File Loader, tokenisation, the publish gate and the CI check.
- **Contents.** File and kind.
- **How a contract is laid out.** A table mapping each ODCS section to what it holds here, with
  `customProperties` for the platform settings the standard has no field for.
- **Changing a contract.** Three bullets:
  - a contract is reviewed like code, and versioned with semantic versioning (a breaking change
    is a major version);
  - never auto-adapt a contract for data that carries money;
  - metrics live in Cube, not here.

## Small doc touch-points

- **Design doc §7.3:** "Each table has a **contract**" gains "in the Open Data Contract Standard
  format ([samples](../../contracts/README.md))".
- **`00-decision-register.md`:** one new lightweight-decision row:
  - Decision: data contracts in ODCS v3.2;
  - Alternative: a home-grown YAML format;
  - Consequence: platform-specific settings sit under `customProperties`;
  - Revisit when: —.
- **`README.md`:** update the `contracts/` tree block to the new layout.

## Not changed now (code; flagged for the code rewrite)

- `src/lakehouse/serve/contract.py` and `tests/test_validator.py` load
  `metrics/transactions.yml`. They are removed with the semantic validator.
- `tests/contract_lint.py` reads the old format. It gets rewritten for ODCS, or replaced with
  `datacontract lint`.
- Comments in `tables/iceberg/03_gold.sql` that mention `contracts/enums.yml`.

## Verification

- Every `.odcs.yaml` parses. Validate it against the official ODCS v3.2.0 JSON schema if
  `jsonschema` is available in `.venv`; this is a read-only check and runs no tests.
- `grep` in `contracts/` finds no "quarantin", "design.md", "generated_at" or "pinned_replica".
- Every ADR-04 §2 item, and the ADR-02 retention class, appears in the matching sample.
- A link check across `docs/`, `contracts/README.md` and `README.md` finds no new broken links.
