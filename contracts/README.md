# Data Contracts

A data contract is the agreement between the team that produces a dataset and everyone who reads
it. It says what the dataset contains, who owns it, how fresh it is, and which checks it must
pass. The contracts here follow the
[Open Data Contract Standard (ODCS)](https://bitol-io.github.io/open-data-contract-standard/)
v3.2.0, from the Bitol project at the Linux Foundation.

**Scope.** These are samples, one of each kind, to show what a contract holds. A full set of
contracts, and validating them in CI, are out of scope for this design.

## Why the Platform Needs Them

The platform's runtime is generic. Everything specific to a source or a table lives in its
contract, so adding a source means adding a contract, not writing code.

| Read by | What it takes from the contract | Decision |
|---|---|---|
| File Loader | Delivery mode, version order, cut-off, arrival window, trailer, truncation threshold, and the reference and optional flags | [ADR-04](../docs/decisions/04-partner-and-ops-files.md) |
| Tokenisation | The classification of every column, and the retention class of each personal field | [ADR-02](../docs/decisions/02-personal-data-tokenisation.md) |
| Publish gate | Each gold table's declared inputs and checks | [ADR-05](../docs/decisions/05-the-publish-gate.md) |
| Contract check in CI | Allowed values, which catch upstream drift that reconciliation can't see | [Design doc](../docs/architecture/lakehouse-design.md) §7.3 |

## Contents

| File | Kind |
|---|---|
| [sources/lending.loan.odcs.yaml](sources/lending.loan.odcs.yaml) | A database table, captured by CDC |
| [sources/partner.acme.odcs.yaml](sources/partner.acme.odcs.yaml) | A partner file feed |
| [gold/fact_transaction.odcs.yaml](gold/fact_transaction.odcs.yaml) | A gold table |

## How a Contract Is Laid Out

| Section | Holds |
|---|---|
| Fundamentals: `apiVersion`, `id`, `name`, `version`, `status`, `domain`, `description` | Identity, purpose and usage |
| `schema` | Columns: types, keys, classification, and checks on each column |
| `quality` | Checks on the table as a whole |
| `slaProperties` | Freshness (`latency`), delivery `frequency`, and `retention` |
| `team` | The owner |
| `customProperties` | Platform settings the standard has no field for, such as version order or declared inputs |

## Changing a Contract

- **A change is reviewed like code.** The contract's `version` follows semantic versioning, so a
  breaking change (removing a column, or changing a type or a key) is a new major version.
- **Never auto-adapt a contract for data that carries money.** A partner's layout change means a
  new contract version, agreed with that partner.
- **Metric definitions aren't contracts.** They live in Cube's data model
  ([ADR-07](../docs/decisions/07-bi-serving.md)).
