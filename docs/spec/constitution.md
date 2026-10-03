# Constitution

The rules every change must keep. An AI assistant working in this repository treats these as
non-negotiable; a plan that would break one is rejected, however convenient. Changing a rule
itself needs an architecture decision record.

## I. Verified Before Visible

No gold table becomes readable until it is proven complete and correct. Build on a branch, check,
then publish in one atomic step, or hold and keep serving the previous version.

## II. Money Is Exact

Money is a signed integer number of paise; rates are integer basis points. Never float or
decimal. Reconciliation tolerance is zero.

## III. Source Order, Never Arrival Order

The result depends only on the source's own order: a change-log position, a partner's sequence
number, an incarnation after a restore. Never a timestamp from a clock we don't own, and never
the order in which data happened to arrive.

## IV. Every Answer Is Labelled

Everything served from the lake states its version, how fresh it is, and whether it was
verified. An unlabelled number is treated as wrong.

## V. Personal Data Is Tokenised First

Personal data becomes a vault token before anything stores it. If the vault is down, ingestion
stops; it never passes clear text through.

## VI. Proven by Tests That Can Fail

- Tests run on a real Iceberg engine, not mocks, and assert the specific wrong answer a broken
  design would give.
- Every guard has a mutation in `tests/mutation/run.py`, and breaking it must make a test fail.

## VII. Safe at the Boundary

Anything a partner or source sends (names, identifiers, file contents) is validated before it
reaches SQL or a table. Secrets, real customer data and company-confidential text never enter
the repository.

## VIII. Standard and Simple

Prefer an industry-standard tool or pattern to an invented one. Keep code readable: domain names,
small functions, short docstrings that state the guarantee. Depth over coverage.

## IX. Written Down

A decision gets an ADR, a test gets an ID in the test plan, a failure mode gets a runbook row,
and this spec is updated in the same change.
