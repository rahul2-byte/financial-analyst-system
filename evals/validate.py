"""Run offline benchmark artifact integrity checks without providers."""

import importlib
import sys
from pathlib import Path

_benchmark_module = importlib.import_module(
    "evals.benchmark" if __package__ else "benchmark"
)
validate_benchmark_artifacts = _benchmark_module.validate_benchmark_artifacts


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
