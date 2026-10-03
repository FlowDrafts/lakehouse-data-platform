"""Check that every value a Cube metric filters on is allowed by the table's data contract.

Reconciliation cannot catch this drift. If the source adds PARTIALLY_SETTLED and a metric
filters on status = 'SETTLED', both sides of every comparison move together: totals still tie,
and every dashboard quietly shows a different number. So the allowed values live in the
contract (as an ODCS `invalidValues` rule), and this check fails the build when a metric relies
on a value the contract does not list, or on a column or table the contracts do not describe.

    .venv/bin/python tests/contract_check.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
FILTER = re.compile(r"\{CUBE\}\.(\w+)\s*=\s*'([^']*)'")


def allowed_values_by_table() -> dict[str, dict[str, set[str] | None]]:
    """For each contracted table: column -> allowed values, or None if the column is unrestricted."""
    tables: dict[str, dict[str, set[str] | None]] = {}
    for path in sorted((REPO / "contracts").rglob("*.odcs.yaml")):
        contract = yaml.safe_load(path.read_text())
        for obj in contract.get("schema", []):
            columns: dict[str, set[str] | None] = {}
            for prop in obj.get("properties", []):
                rules = [q for q in prop.get("quality", []) if q.get("metric") == "invalidValues"]
                values = rules[0].get("arguments", {}).get("validValues") if rules else None
                columns[prop["name"]] = set(values) if values else None
            tables[obj["physicalName"]] = columns
    return tables


def problems_in_cube_model() -> list[str]:
    contracts = allowed_values_by_table()
    problems = []
    for path in sorted((REPO / "deploy" / "cube" / "model").glob("*.yml")):
        for cube in yaml.safe_load(path.read_text()).get("cubes", []):
            table = cube["sql_table"]
            columns = next((c for name, c in contracts.items() if name.endswith(table)), None)
            if columns is None:
                problems.append(f"{path.name}: no contract describes {table}")
                continue
            for measure in cube.get("measures", []):
                for condition in measure.get("filters", []):
                    for column, value in FILTER.findall(condition["sql"]):
                        if column not in columns:
                            problems.append(
                                f"{measure['name']}: {column} is not in {table}'s contract"
                            )
                        elif columns[column] is not None and value not in columns[column]:
                            problems.append(
                                f"{measure['name']}: filters {column} = '{value}', which the "
                                f"contract for {table} does not allow"
                            )
    return problems


def main() -> int:
    problems = problems_in_cube_model()
    for problem in problems:
        print(f"  DRIFT  {problem}")
    print("Cube model matches the contracts." if not problems else f"{len(problems)} problem(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
