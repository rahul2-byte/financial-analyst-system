"""Validation helpers for the frozen offline evaluation set."""

from __future__ import annotations

from pathlib import Path

from evals.run import load_jsonl


def validate_frozen_benchmark(tasks_path: Path, expected_cases: int) -> list[str]:
    """Return structural errors without evaluating model quality."""
    tasks = load_jsonl(tasks_path)
    errors: list[str] = []
    ids = [str(task.get("id", "")) for task in tasks]
    if len(tasks) != expected_cases:
        errors.append(f"expected {expected_cases} tasks, found {len(tasks)}")
    if any(not case_id for case_id in ids):
        errors.append("all tasks require an id")
    if len(set(ids)) != len(ids):
        errors.append("task ids must be unique")
    return errors
