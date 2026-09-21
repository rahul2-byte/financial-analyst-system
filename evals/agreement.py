"""Agreement metrics for independent claim labels."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def cohens_kappa(first: Sequence[str], second: Sequence[str]) -> float:
    if len(first) != len(second) or not first:
        raise ValueError("label sequences must have equal non-zero length")
    observed = sum(a == b for a, b in zip(first, second, strict=True)) / len(first)
    categories = set(first) | set(second)
    expected = sum(
        (first.count(category) / len(first)) * (second.count(category) / len(second))
        for category in categories
    )
    return 1.0 if expected == 1.0 else round((observed - expected) / (1 - expected), 6)


def agreement_summary(labels: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], dict[str, str]] = {}
    for label in labels:
        grouped.setdefault((str(label.get("case_id")), str(label.get("claim_id"))), {})[
            str(label.get("labeler_id"))
        ] = str(label.get("semantic_judgment"))
    pairs = [tuple(values.values()) for values in grouped.values() if len(values) >= 2]
    first = [pair[0] for pair in pairs]
    second = [pair[1] for pair in pairs]
    return {
        "labeled_items": len(pairs),
        "raw_agreement": sum(a == b for a, b in zip(first, second, strict=True)) / len(pairs)
        if pairs
        else None,
        "cohens_kappa": cohens_kappa(first, second) if pairs else None,
    }
