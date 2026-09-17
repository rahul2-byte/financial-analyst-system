"""Run FIN-AI evaluation records against versioned local gold tasks."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    _metrics: Any = importlib.import_module("evals.metrics")
except ModuleNotFoundError:  # Direct ``python evals/run.py`` execution.
    _metrics = importlib.import_module("metrics")

aggregate_metrics = _metrics.aggregate_metrics
evaluate_case = _metrics.evaluate_case
ndcg_at_k = _metrics.ndcg_at_k
recall_at_k = _metrics.recall_at_k
reciprocal_rank = _metrics.reciprocal_rank


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError(f"{path}:{line_number}: expected a JSON object")
        records.append(value)
    return records


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _evidence_metrics(task: dict[str, Any], result: dict[str, Any]) -> dict[str, float]:
    expected = {str(item) for item in task.get("relevant_evidence_ids", [])}
    ranked = [str(item) for item in result.get("retrieved_evidence_ids", [])]
    return {
        "recall_at_5": recall_at_k(ranked, expected, 5),
        "recall_at_10": recall_at_k(ranked, expected, 10),
        "mrr_at_10": reciprocal_rank(ranked[:10], expected),
        "ndcg_at_10": ndcg_at_k(ranked, expected, 10),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    tasks = load_jsonl(Path(args.tasks))
    results = {str(item.get("id")): item for item in load_jsonl(Path(args.results))}
    case_metrics: list[dict[str, Any]] = []
    missing_results: list[str] = []
    for task in tasks:
        case_id = str(task.get("id"))
        result = results.get(case_id)
        if result is None:
            missing_results.append(case_id)
            continue
        metrics = evaluate_case(task, result)
        metrics["evidence_selection"] = _evidence_metrics(task, result)
        case_metrics.append(metrics)

    manifest = Path(args.manifest)
    complete_gold_set = len(tasks) == args.expected_cases and not missing_results
    payload = {
        "status": "measured" if complete_gold_set else "insufficient_evidence",
        "metadata": {
            "git_commit": git_commit(),
            "gold_set_version": Path(args.tasks).parent.name,
            "source_manifest_hash": sha256_file(manifest)
            if manifest.exists()
            else None,
            "prompt_version": args.prompt_version,
            "model_id": args.model_id,
            "configuration_hash": args.configuration_hash,
            "run_timestamp": datetime.now(UTC).isoformat(),
            "random_seed": args.random_seed,
            "mode": args.mode,
            "expected_gold_cases": args.expected_cases,
        },
        "metrics": aggregate_metrics(case_metrics),
        "missing_results": missing_results,
        "notes": [
            "No benchmark claim is valid unless status is measured and the gold set is complete.",
            "Live mode is diagnostic and must not be merged into offline scores.",
        ],
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument("--tasks", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-id", default=None)
    parser.add_argument("--prompt-version", default=None)
    parser.add_argument("--configuration-hash", default=None)
    parser.add_argument("--random-seed", type=int, default=None)
    parser.add_argument("--expected-cases", type=int, default=100)
    args = parser.parse_args()
    output = run(args)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
