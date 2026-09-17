from pathlib import Path

from evals.benchmark import validate_frozen_benchmark


def test_frozen_benchmark_is_structurally_complete() -> None:
    path = Path("evals/gold/v1/tasks.jsonl")
    assert validate_frozen_benchmark(path, expected_cases=10) == []
