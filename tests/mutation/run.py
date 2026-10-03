"""Mutation testing: break each guard on purpose, and require a test to fail.

A passing suite proves nothing about whether it would fail. Each entry below removes or loosens
one guard in the source, runs the tests that should notice, and restores the file. A mutation
that no test catches is a guarantee the code claims but does not actually hold.

    .venv/bin/python tests/mutation/run.py                 # every mutation (about 20 minutes)
    .venv/bin/python tests/mutation/run.py --only cut      # by name
    .venv/bin/python tests/mutation/run.py --check         # find-strings only, about a second

The exit code is non-zero if any mutation survives, or if its find-string no longer matches the
source (a stale mutation means the guard is no longer being checked).
"""

from __future__ import annotations

import argparse
import enum
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PYTEST = REPO / ".venv" / "bin" / "pytest"

MERGE = "src/lakehouse/ingestion/cdc_merge.py"
CUT = "src/lakehouse/ingestion/transaction_cut.py"
FILES = "src/lakehouse/ingestion/partner_files.py"
GATE = "src/lakehouse/publishing/publish_gate.py"


@dataclass(frozen=True)
class Mutation:
    name: str
    file: str
    find: str
    replace: str
    tests: str
    breaks: str  # the guarantee that would be lost


MUTATIONS = [
    # ---- the ordered merge (baseline) ------------------------------------------------------
    Mutation(
        "merge-applies-only-newer-changes",
        MERGE,
        "WHEN MATCHED AND {is_newer} THEN",
        "WHEN MATCHED THEN",
        "tests/test_cdc_merge.py",
        "an older change arriving late overwrites a newer one",
    ),
    Mutation(
        "merge-delete-clears-values",
        MERGE,
        "UPDATE SET {clear_values}, t.is_deleted = true",
        "UPDATE SET t.is_deleted = true",
        "tests/test_cdc_merge.py",
        "a deleted row keeps whatever values arrived before the delete",
    ),
    Mutation(
        "merge-stores-unseen-deletes",
        MERGE,
        "WHEN NOT MATCHED AND s.op = 'd' THEN",
        "WHEN NOT MATCHED AND s.op = 'never' THEN",
        "tests/test_cdc_merge.py",
        "a delete arriving before its insert is lost, and the insert revives the row",
    ),
    Mutation(
        "merge-fails-on-truncate",
        MERGE,
        "SUPPORTED_OPERATIONS = \"'c', 'u', 'd', 'r'\"",
        "SUPPORTED_OPERATIONS = \"'c', 'u', 'd', 'r', 't'\"",
        "tests/test_cdc_merge.py",
        "a truncate writes nulls over real values",
    ),
    Mutation(
        "merge-orders-by-incarnation",
        MERGE,
        "(s.source_incarnation = t.source_incarnation AND s.source_lsn > t.source_lsn)",
        "(s.source_lsn > t.source_lsn)",
        "tests/test_cdc_merge.py",
        "after a restore, new changes look older and are ignored",
    ),
    Mutation(
        "merge-keeps-unchanged-large-values",
        MERGE,
        "return f\"CASE WHEN s.{column} = '{UNCHANGED_PLACEHOLDER}' THEN t.{column} ELSE s.{column} END\"",
        'return f"s.{column}"',
        "tests/test_cdc_merge.py",
        "an unchanged large column is overwritten by Debezium's placeholder",
    ),
    # ---- the transaction cut (hidden problem) ----------------------------------------------
    Mutation(
        "cut-is-a-prefix",
        CUT,
        "            break\n",
        "            continue\n",
        "tests/test_transaction_cut.py",
        "a later transaction is published while an earlier one is still incomplete",
    ),
    Mutation(
        "cut-needs-every-table",
        CUT,
        "if any(landed.get(",
        "if all(landed.get(",
        "tests/test_transaction_cut.py",
        "a loan is published while its ledger lines are still in flight",
    ),
    Mutation(
        "cut-completeness-needs-the-cutoff",
        CUT,
        "if cut is not None and cut.committed_at >= cutoff:",
        "if cut is not None:",
        "tests/test_transaction_cut.py",
        "a day is declared complete before the source has passed its cut-off",
    ),
    Mutation(
        "cut-is-safe-to-rerun",
        CUT,
        "CREATE TAG IF NOT EXISTS",
        "CREATE TAG",
        "tests/test_transaction_cut.py::test_rerunning_a_cut_after_a_failure_is_safe",
        "a cut that failed partway can never be rerun",
    ),
    # ---- partner files (genuine problem 1) -------------------------------------------------
    Mutation(
        "files-version-needs-every-part",
        FILES,
        'if len(parts) < parts[0]["part_count"]:',
        "if False:",
        "tests/test_partner_files.py::test_a_version_in_parts_publishes_only_when_every_part_has_arrived",
        "a version publishes with parts missing, mixing two versions",
    ),
    Mutation(
        "files-only-a-newer-version-wins",
        FILES,
        "WHEN NOT MATCHED AND s.sequence_number > s.current_sequence THEN",
        "WHEN NOT MATCHED THEN",
        "tests/test_partner_files.py::test_an_older_version_arriving_late_never_becomes_current",
        "an older version arriving late becomes current",
    ),
    Mutation(
        "files-flip-is-scoped-to-the-delivery",
        FILES,
        'WHEN NOT MATCHED BY SOURCE AND {delivery.where("t")}',
        "WHEN NOT MATCHED BY SOURCE",
        "tests/test_partner_files.py::test_a_correction_replaces_the_previous_version_and_history_keeps_both",
        "publishing one delivery withdraws another delivery's current version",
    ),
    Mutation(
        "files-append-once",
        FILES,
        '.overwrite(F.col("file_id") == part.file_id)',
        ".append()",
        "tests/test_partner_files.py::test_a_rerun_after_a_crash_does_not_load_the_rows_twice",
        "a rerun after a crash loads the same rows twice",
    ),
    Mutation(
        "files-truncation-guard",
        FILES,
        "if approved_by is None and usual and",
        "if approved_by is None and False and",
        "tests/test_partner_files.py::test_a_truncated_file_whose_trailer_matches_is_held_for_approval",
        "a truncated file whose trailer matches is published",
    ),
    Mutation(
        "files-identifiers-are-validated",
        FILES,
        "require_safe(partner=self.partner, feed=self.feed)",
        "pass",
        "tests/test_partner_files.py::test_a_partner_identifier_that_could_change_the_sql_is_refused",
        "a partner name can change the meaning of the SQL",
    ),
    # ---- the publish gate (genuine problem 2) ----------------------------------------------
    Mutation(
        "gate-checks-the-fingerprint",
        GATE,
        'MEASURES = ("row_count", "amount_paise", "distinct_keys", "fingerprint")',
        'MEASURES = ("row_count", "amount_paise", "distinct_keys")',
        "tests/test_publish_gate.py",
        "money moved between customers passes the gate",
    ),
    Mutation(
        "gate-compares-both-sides",
        GATE,
        '"full_outer")',
        '"left_outer").where(F.col("r.row_count").isNotNull())',
        "tests/test_publish_gate.py::test_a_cell_only_the_build_has_is_a_break",
        "a day the source never reported (a double load) passes",
    ),
    Mutation(
        "gate-replaces-the-whole-window",
        GATE,
        "writer.overwrite(in_window)",
        "writer.append()",
        "tests/test_publish_gate.py::test_a_date_with_no_rows_now_becomes_empty_instead_of_keeping_old_rows",
        "a date with no rows keeps the previous run's rows",
    ),
    Mutation(
        "gate-holds-on-incomplete-inputs",
        GATE,
        'reasons = [f"input not complete: {i.name} ({i.detail})" for i in inputs if not i.complete]',
        "reasons = []",
        "tests/test_publish_gate.py::test_an_incomplete_input_holds_the_table_and_readers_keep_the_previous_version",
        "a table publishes before its inputs are complete",
    ),
]


class Result(enum.Enum):
    CAUGHT = "caught"
    SURVIVED = "SURVIVED"
    STALE = "STALE"  # the find-string no longer matches, so the guard is not being checked


def run(mutation: Mutation) -> tuple[Result, str]:
    """Apply one mutation, run its tests, and always restore the file."""
    path = REPO / mutation.file
    original = path.read_text()
    if mutation.find not in original:
        return Result.STALE, "find-string not in the source"
    try:
        path.write_text(original.replace(mutation.find, mutation.replace, 1))
        process = subprocess.run(
            [str(PYTEST), *mutation.tests.split(), "-x", "-q", "-p", "no:cacheprovider"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        if process.returncode == 0:
            return Result.SURVIVED, "no test failed"
        failed = next((ln for ln in process.stdout.splitlines() if ln.startswith("FAILED")), "")
        return Result.CAUGHT, failed.split("::")[-1].split(" ")[0] or "a test failed"
    except subprocess.TimeoutExpired:
        return Result.SURVIVED, "timed out"
    finally:
        path.write_text(original)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="", help="run mutations whose name contains this")
    parser.add_argument("--check", action="store_true", help="check find-strings only")
    args = parser.parse_args()

    selected = [m for m in MUTATIONS if args.only in m.name]
    if args.check:
        stale = [m for m in selected if m.find not in (REPO / m.file).read_text()]
        for m in stale:
            print(f"  STALE  {m.name}: find-string not in {m.file}")
        print(f"{len(selected) - len(stale)} of {len(selected)} find-strings match.")
        return 1 if stale else 0

    print(f"Breaking {len(selected)} guards on purpose. Each must make a test fail.\n")
    failures = 0
    for mutation in selected:
        result, detail = run(mutation)
        print(f"  {result.value:8}  {mutation.name:40} {detail}")
        if result is not Result.CAUGHT:
            print(f"            unguarded: {mutation.breaks}")
            failures += 1
    print(f"\n{len(selected) - failures} of {len(selected)} mutations caught.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
