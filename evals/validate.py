"""Run offline benchmark artifact integrity checks without providers."""

import sys
from pathlib import Path

from evals.benchmark import validate_benchmark_artifacts


def main() -> int:
    root = Path(__file__).resolve().parent / "gold" / "v1"
    errors = validate_benchmark_artifacts(
        root / "tasks.jsonl",
        root / "baseline-results.jsonl",
        root / "source-manifest.json",
        expected_cases=10,
    )
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("benchmark artifacts valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
