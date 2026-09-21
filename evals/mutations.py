"""Deterministic report mutation accounting for validator evaluations."""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.agent_loop.publication import (
    EvidenceFact,
    PublicationError,
    ReportDraft,
    publish_report,
)

MutationValidator = Callable[[str, dict[str, Any]], bool]


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    reasons: tuple[str, ...] = ()


def publish_validator(draft: ReportDraft, evidence: dict[str, EvidenceFact]) -> ValidationResult:
    """Validate a structured draft using the production publication boundary."""
    try:
        publish_report(draft, evidence)
    except PublicationError as exc:
        return ValidationResult(False, exc.reasons)
    return ValidationResult(True)


def evaluate_publish_mutations(records: list[dict[str, Any]], seed: int = 0) -> dict[str, Any]:
    """Evaluate structured JSON fixtures through the production publisher."""
    clean: list[tuple[ReportDraft, dict[str, EvidenceFact]]] = []
    for record in records:
        draft = ReportDraft.model_validate(record["draft"])
        evidence = {
            key: EvidenceFact.model_validate(value)
            for key, value in dict(record.get("evidence") or {}).items()
        }
        clean.append((draft, evidence))
    clean_results = [publish_validator(draft, evidence) for draft, evidence in clean]
    return {
        "clean": {
            "n": len(clean_results),
            "accepted": sum(result.passed for result in clean_results),
            "false_block_rate": sum(not result.passed for result in clean_results) / len(clean_results) if clean_results else 0.0,
        },
        "status": "evaluated",
        "seed": seed,
    }


def load_clean_reports(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict) or not isinstance(value.get("report"), str):
            raise TypeError(f"{path}:{line_number}: report record is invalid")
        records.append(value)
    return records


def _replace_first(report: str, old: str, new: str) -> str | None:
    if old not in report:
        return None
    return report.replace(old, new, 1)


def _mutations(report: str, rng: random.Random) -> dict[str, str | None]:
    del rng
    marker_start = report.find("[[fact:")
    marker_end = report.find("]]", marker_start)
    marker = report[marker_start : marker_end + 2] if marker_start >= 0 and marker_end >= 0 else None
    return {
        "delete_numeric_marker": _replace_first(report, marker, "10") if marker else None,
        "wrong_numeric_literal": _replace_first(report, "10", "999999") if "10" in report else None,
        "delete_citation": _replace_first(report, "citation-1", "missing-citation"),
        "unsupported_forward_claim": f"{report}\nThis guarantees future returns.",
    }


def evaluate_mutations(
    records: list[dict[str, Any]],
    *,
    validator: MutationValidator | None = None,
    seed: int = 0,
) -> dict[str, Any]:
    rng = random.Random(seed)
    clean_blocked = 0
    if validator is not None:
        for record in records:
            clean_blocked += int(not validator(str(record["report"]), dict(record.get("evidence") or {})))
    output: dict[str, Any] = {
        "clean": {"false_block_count": clean_blocked, "n": len(records)},
        "mutations": {},
        "seed": seed,
    }
    names = ("delete_numeric_marker", "wrong_numeric_literal", "delete_citation", "unsupported_forward_claim")
    for name in names:
        applied = caught = crashed = 0
        for record in records:
            mutated = _mutations(str(record["report"]), rng).get(name)
            if mutated is None or mutated == record["report"]:
                continue
            applied += 1
            if validator is None:
                continue
            try:
                caught += int(not validator(mutated, dict(record.get("evidence") or {})))
            except (KeyError, TypeError, ValueError, RuntimeError):
                crashed += 1
        output["mutations"][name] = {
            "caught": caught,
            "crashed": crashed,
            "n": applied,
            "recall": caught / applied if applied else None,
            "status": "not_evaluated" if validator is None else "evaluated",
        }
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", type=Path, required=True)
    parser.add_argument("--structured", action="store_true")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if args.structured:
        records = [json.loads(line) for line in args.clean.read_text(encoding="utf-8").splitlines() if line.strip()]
        result = evaluate_publish_mutations(records, seed=args.seed)
    else:
        result = evaluate_mutations(load_clean_reports(args.clean), seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
