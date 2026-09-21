"""Validate and score approved replay evaluation cases."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

_OUTCOMES = {"answer", "evidence_gap", "refuse"}
_HASH = set("0123456789abcdef")


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HASH


def validate_pilot_cases(cases: list[dict[str, Any]], archive_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    ids = [str(case.get("id", "")) for case in cases]
    if not cases:
        return ["at least one case is required"]
    if any(not case_id for case_id in ids) or len(set(ids)) != len(ids):
        errors.append("case ids must be present and unique")
    for case in cases:
        case_id = str(case.get("id", ""))
        if case.get("expected_outcome") not in _OUTCOMES:
            errors.append(f"{case_id}: invalid expected_outcome")
        if not case.get("expected_terminal_status"):
            errors.append(f"{case_id}: expected_terminal_status is required")
        snapshots = case.get("replay_snapshots")
        snapshot_values = []
        if isinstance(snapshots, dict):
            for value in snapshots.values():
                snapshot_values.extend(value if isinstance(value, list) else [value])
        if not isinstance(snapshots, dict) or not snapshot_values or any(not _is_hash(value) for value in snapshot_values):
            errors.append(f"{case_id}: replay_snapshots requires a SHA-256 hash")
        elif archive_root is not None:
            from app.observability.provider_archive import (
                ProviderArchive,
                ProviderArchiveError,
            )

            archive = ProviderArchive(archive_root)
            for value in snapshots.values():
                hashes = value if isinstance(value, list) else [value]
                for content_hash in hashes:
                    try:
                        archive.load(str(content_hash))
                    except ProviderArchiveError as exc:
                        errors.append(f"{case_id}: {exc}")
        source_hashes = case.get("source_hashes")
        if not isinstance(source_hashes, list) or any(not _is_hash(value) for value in source_hashes):
            errors.append(f"{case_id}: source_hashes must contain SHA-256 hashes")
    return errors


def _fact_score(case: dict[str, Any], result: dict[str, Any]) -> bool:
    outputs = result.get("numeric_outputs", {})
    for fact in case.get("required_facts", []):
        if not isinstance(fact, dict) or fact.get("field") not in outputs:
            return False
        try:
            if abs(float(outputs[fact["field"]]) - float(fact["value"])) > float(fact.get("tolerance", 0)):
                return False
        except (TypeError, ValueError):
            return False
    return True


def score_results(cases: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(item.get("case_id")): item for item in results}
    rows: list[dict[str, Any]] = []
    for case in cases:
        result = by_id.get(str(case.get("id")))
        actual_status = result.get("terminal_status") if result else "missing"
        status_ok = actual_status == case.get("expected_terminal_status")
        facts_ok = _fact_score(case, result or {})
        outcome_ok = status_ok and facts_ok
        rows.append({"case_id": case.get("id"), "passed": outcome_ok, "status_ok": status_ok, "facts_ok": facts_ok})
    passed = sum(bool(row["passed"]) for row in rows)
    denominator = len(rows)
    interval = None
    if denominator:
        z = 1.96
        proportion = passed / denominator
        scale = 1 + z * z / denominator
        centre = (proportion + z * z / (2 * denominator)) / scale
        half = z * math.sqrt(proportion * (1 - proportion) / denominator + z * z / (4 * denominator**2)) / scale
        interval = [max(0.0, centre - half), min(1.0, centre + half)]
    return {
        "case_count": denominator,
        "task_success": {"count": passed, "denominator": denominator, "wilson_95": interval},
        "cases": rows,
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--cases", type=Path, required=True)
    validate.add_argument("--archive-root", type=Path)
    score = sub.add_parser("score")
    score.add_argument("--cases", type=Path, required=True)
    score.add_argument("--results", type=Path)
    score.add_argument("--results-dir", type=Path)
    score.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "validate":
        errors = validate_pilot_cases(_load_jsonl(args.cases), args.archive_root)
        for error in errors:
            print(error)
        return int(bool(errors))
    if bool(args.results) == bool(args.results_dir):
        parser.error("score requires exactly one of --results or --results-dir")
    result_paths = [args.results] if args.results else sorted(args.results_dir.glob("*.json"))
    results = [json.loads(path.read_text(encoding="utf-8")) for path in result_paths]
    result = score_results(_load_jsonl(args.cases), results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
