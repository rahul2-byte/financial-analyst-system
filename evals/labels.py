"""Validation for independent human citation and claim labels."""

from __future__ import annotations

from typing import Any


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
