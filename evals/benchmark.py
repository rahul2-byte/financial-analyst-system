"""Validation helpers for the frozen offline evaluation set."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

_run_module = importlib.import_module("evals.run" if __package__ else "run")
load_jsonl = _run_module.load_jsonl


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


def validate_benchmark_artifacts(
    tasks_path: Path,
    results_path: Path,
    manifest_path: Path,
    expected_cases: int,
) -> list[str]:
    """Validate that task, result, and source-manifest artifacts agree."""
    errors = validate_frozen_benchmark(tasks_path, expected_cases)
    tasks = load_jsonl(tasks_path)
    results = load_jsonl(results_path)
    task_ids = {str(item.get("id", "")) for item in tasks}
    result_ids = [str(item.get("id", "")) for item in results]
    if len(result_ids) != len(set(result_ids)):
        errors.append("result ids must be unique")
    if set(result_ids) != task_ids:
        errors.append("results must match task ids exactly")
    if not manifest_path.is_file():
        errors.append("source manifest is missing")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not manifest.get("version"):
            errors.append("source manifest requires a version")
        if manifest.get("status") == "seeded_fixture":
            return errors
        sources = manifest.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append("source manifest requires at least one source")
            return errors
        for source in sources:
            if not isinstance(source, dict):
                errors.append("source manifest entries must be objects")
                continue
            if not source.get("sha256") or not source.get("retrieved_at"):
                errors.append(f"source {source.get('id', '')} lacks hash or timestamp")
    return errors


def classify_benchmark_artifacts(
    tasks_path: Path,
    results_path: Path,
    manifest_path: Path,
    expected_cases: int,
) -> str:
    """Classify a complete artifact set without claiming quality for fixtures."""
    errors = validate_benchmark_artifacts(
        tasks_path, results_path, manifest_path, expected_cases
    )
    if errors:
        return "insufficient_evidence"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") == "seeded_fixture":
        return "synthetic_contract"
    return "market_quality_measured"
