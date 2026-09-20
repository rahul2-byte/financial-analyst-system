"""Validation for independent human citation and claim labels."""

from __future__ import annotations

from typing import Any

from evals.snapshots import validate_candidate_source_record

_CANDIDATE_CATEGORIES = {
    "fundamentals",
    "technical",
    "news_source",
    "conflicting_evidence",
    "insufficient_evidence",
}
_CLAIM_JUDGMENTS = {"supports", "contradicts", "unsupported"}


def validate_human_labels(labels: list[dict[str, Any]]) -> list[str]:
    """Return integrity errors for two-labeler records."""
    errors: list[str] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for label in labels:
        item_id = str(label.get("item_id", ""))
        grouped.setdefault(item_id, []).append(label)
        if not item_id:
            errors.append("every label requires an item_id")
        if not label.get("labeler_id"):
            errors.append(f"{item_id}: labeler_id is required")
        if not label.get("evidence_span"):
            errors.append(f"{item_id}: evidence_span is required")
    for item_id, records in grouped.items():
        labelers = [str(record.get("labeler_id")) for record in records]
        if len(set(labelers)) < 2:
            errors.append(f"{item_id}: requires two independent labelers")
        judgments = {str(record.get("judgment")) for record in records}
        if len(judgments) > 1 and not any(
            record.get("adjudicated") for record in records
        ):
            errors.append(f"{item_id}: disagreement requires adjudication")
    return errors


def validate_claim_support_labels(labels: list[dict[str, Any]]) -> list[str]:
    """Validate structured human labels for major claim/source pairs."""
    errors: list[str] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    required = ("case_id", "claim_id", "labeler_id", "source_id", "evidence_span")
    for label in labels:
        case_id = str(label.get("case_id", ""))
        claim_id = str(label.get("claim_id", ""))
        key = (case_id, claim_id)
        grouped.setdefault(key, []).append(label)
        for field in required:
            if not label.get(field):
                errors.append(f"{case_id}/{claim_id}: {field} is required")
        numeric = label.get("numeric_value_correct")
        if numeric is not None and not isinstance(numeric, bool):
            errors.append(
                f"{case_id}/{claim_id}: numeric_value_correct must be boolean or null"
            )
        if label.get("semantic_judgment") not in _CLAIM_JUDGMENTS:
            errors.append(f"{case_id}/{claim_id}: semantic_judgment is invalid")
    for (case_id, claim_id), records in grouped.items():
        labelers = [str(record.get("labeler_id")) for record in records]
        if len(set(labelers)) < 2:
            errors.append(f"{case_id}/{claim_id}: requires two independent labelers")
        judgments = {
            (
                record.get("numeric_value_correct"),
                record.get("semantic_judgment"),
            )
            for record in records
        }
        if len(judgments) > 1 and not any(
            record.get("adjudicated") for record in records
        ):
            errors.append(f"{case_id}/{claim_id}: disagreement requires adjudication")
    return errors


def validate_candidate_cases(
    cases: list[dict[str, Any]], expected_cases: int = 20
) -> list[str]:
    """Validate unresolved candidate cases before source and human review."""
    errors: list[str] = []
    if len(cases) != expected_cases:
        errors.append(f"expected {expected_cases} candidate cases, found {len(cases)}")
    case_ids = [str(case.get("id", "")) for case in cases]
    if any(not case_id for case_id in case_ids):
        errors.append("every candidate case requires an id")
    if len(set(case_ids)) != len(case_ids):
        errors.append("case ids must be unique")
    if expected_cases == 20:
        for category in _CANDIDATE_CATEGORIES:
            if sum(case.get("category") == category for case in cases) != 4:
                errors.append(f"candidate category requires four cases: {category}")
    for case in cases:
        case_id = str(case.get("id", ""))
        if case.get("status") != "candidate":
            errors.append(f"{case_id}: status must be candidate")
        if case.get("category") not in _CANDIDATE_CATEGORIES:
            errors.append(f"{case_id}: category is invalid")
        if not case.get("question"):
            errors.append(f"{case_id}: question is required")
        expected_evidence = case.get("expected_evidence")
        if not isinstance(expected_evidence, dict) or not expected_evidence.get(
            "status"
        ):
            errors.append(f"{case_id}: expected_evidence is required")
        if not case.get("labeling_instructions"):
            errors.append(f"{case_id}: labeling_instructions is required")
        source = case.get("source")
        if not isinstance(source, dict):
            errors.append(f"{case_id}: source is required")
        else:
            errors.extend(
                f"{case_id}: {error}"
                for error in validate_candidate_source_record(source)
            )
        if case.get("labels") != []:
            errors.append(f"{case_id}: labels must remain empty")
    return errors
