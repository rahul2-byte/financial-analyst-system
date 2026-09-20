"""Paired summaries for replay-only runtime ablations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AblationVariant:
    name: str
    source_quality_filtering: bool
    publish_reports: bool


ABLATION_VARIANTS = (
    AblationVariant("baseline", False, False),
    AblationVariant("quality_only", True, False),
    AblationVariant("publication_only", False, True),
    AblationVariant("full", True, True),
)


def variant_configuration(
    base_configuration: dict[str, Any], variant_name: str
) -> dict[str, Any]:
    try:
        variant = next(item for item in ABLATION_VARIANTS if item.name == variant_name)
    except StopIteration as exc:
        raise ValueError(f"unknown ablation variant: {variant_name}") from exc
    configuration = dict(base_configuration)
    configuration.update(
        {
            "source_quality_filtering": variant.source_quality_filtering,
            "publish_reports": variant.publish_reports,
        }
    )
    return configuration


def _count(count: int, denominator: int) -> dict[str, int]:
    return {"count": count, "denominator": denominator}


def _source_quality(artifacts: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    totals = {"raw_count": 0, "quality_filtered_count": 0, "retained_count": 0}
    denominator = 0
    for artifact in artifacts:
        for detail in artifact.get("tool_details", []):
            if detail.get("tool") != "news:fetch_news":
                continue
            try:
                quality = json.loads(str(detail.get("detail") or ""))["news_quality"]
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            denominator += 1
            for field in totals:
                totals[field] += int(quality.get(field, 0))
    return {field: _count(value, denominator) for field, value in totals.items()}


def _variant_summary(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [item for item in artifacts if item.get("terminal_status") == "failed"]
    structured = [
        item
        for item in artifacts
        if item.get("report_validation", {}).get("status") == "structured"
    ]
    failure_examples = []
    for item in artifacts:
        details = item.get("failure_details", [])
        validation = item.get("report_validation", {})
        if item.get("terminal_status") == "failed" or details:
            failure_examples.append(
                {
                    "category": "runtime_failure",
                    "case_id": item.get("case_id"),
                    "terminal_status": item.get("terminal_status"),
                    "failure_details": details,
                }
            )
        if validation.get("status") not in {None, "structured", "pending"}:
            failure_examples.append(
                {
                    "category": "report_validation_failure",
                    "case_id": item.get("case_id"),
                    "reasons": validation.get("reasons", []),
                    "report_excerpt": str(item.get("report", ""))[:500],
                }
            )
    return {
        "scheduled_case_count": len(artifacts),
        "completed_case_count": len(artifacts) - len(failed),
        "failed_case_count": len(failed),
        "terminal_success": _count(
            sum(item.get("terminal_status") == "success" for item in artifacts),
            len(artifacts),
        ),
        "structured_report": _count(len(structured), len(artifacts)),
        "source_quality": _source_quality(artifacts),
        "failure_examples": failure_examples[:50],
    }


def _paired_metric(
    variant_items: list[dict[str, Any]], baseline_items: list[dict[str, Any]], key: str
) -> dict[str, Any]:
    variant_by_case = {str(item.get("case_id")): item for item in variant_items}
    baseline_by_case = {str(item.get("case_id")): item for item in baseline_items}
    paired_ids = sorted(set(variant_by_case) & set(baseline_by_case))
    variant_count = sum(
        variant_by_case[case_id].get(key) == "success" for case_id in paired_ids
    )
    baseline_count = sum(
        baseline_by_case[case_id].get(key) == "success" for case_id in paired_ids
    )
    return {
        "variant": _count(variant_count, len(paired_ids)),
        "baseline": _count(baseline_count, len(paired_ids)),
        "delta_count": variant_count - baseline_count,
    }


def compare_ablation_results(
    artifacts_by_variant: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Summarize variants and paired differences without hiding failures."""
    summaries = {
        name: _variant_summary(artifacts)
        for name, artifacts in artifacts_by_variant.items()
    }
    baseline = artifacts_by_variant.get("baseline", [])
    differences: dict[str, Any] = {}
    for name, artifacts in artifacts_by_variant.items():
        if name == "baseline":
            continue
        paired_ids = sorted(
            {str(item.get("case_id")) for item in artifacts}
            & {str(item.get("case_id")) for item in baseline}
        )
        differences[f"{name}_vs_baseline"] = {
            "paired_case_count": len(paired_ids),
            "terminal_success": _paired_metric(artifacts, baseline, "terminal_status"),
            "report_structured": {
                "variant": _count(
                    sum(
                        item.get("report_validation", {}).get("status") == "structured"
                        for item in artifacts
                        if str(item.get("case_id")) in paired_ids
                    ),
                    len(paired_ids),
                ),
                "baseline": _count(
                    sum(
                        item.get("report_validation", {}).get("status") == "structured"
                        for item in baseline
                        if str(item.get("case_id")) in paired_ids
                    ),
                    len(paired_ids),
                ),
            },
            "failure_examples": [
                example
                for item in (artifacts + baseline)
                if str(item.get("case_id")) in paired_ids
                for example in _variant_summary([item])["failure_examples"]
            ][:50],
        }
    return {"variants": summaries, "differences": differences}
