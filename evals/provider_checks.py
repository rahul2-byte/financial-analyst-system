"""Compare frozen provider values with independently recorded values."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any


def compare_values(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {name: 0 for name in ("agree", "disagree", "not_comparable", "missing_independent_source")}
    for record in records:
        if record.get("independent_value") is None:
            counts["missing_independent_source"] += 1
            continue
        try:
            primary = Decimal(str(record["primary_value"]))
            independent = Decimal(str(record["independent_value"]))
            tolerance = Decimal(str(record.get("tolerance", "0")))
        except (KeyError, ArithmeticError, ValueError):
            counts["not_comparable"] += 1
            continue
        counts["agree" if abs(primary - independent) <= tolerance else "disagree"] += 1
    denominator = len(records)
    return {**counts, "sample_count": denominator, "agreement_rate": counts["agree"] / denominator if denominator else None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.records.read_text(encoding="utf-8").splitlines() if line.strip()]
    result = compare_values(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
