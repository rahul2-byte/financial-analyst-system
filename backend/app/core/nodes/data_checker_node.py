from __future__ import annotations

from typing import Any


FRESHNESS_THRESHOLD = 0.6


async def data_checker_node(state: dict[str, Any]) -> dict[str, Any]:
    data_status = state.get("data_status", {})
    required = ("ohlcv", "news", "fundamentals", "macro")

    missing: list[str] = []
    stale: list[str] = []

    for dataset in required:
        record = data_status.get(dataset, {})
        if not record.get("available", False):
            missing.append(dataset)
            continue
        if float(record.get("freshness", 0.0)) < FRESHNESS_THRESHOLD:
            stale.append(dataset)

    status = "success" if not missing and not stale else "partial"
    next_action = "run_research_plan" if status == "success" else "run_data_plan"

    return {
        "status": status,
        "reasoning": "Checked required dataset availability and freshness against deterministic threshold.",
        "confidence_score": 0.8 if status == "success" else 0.6,
        "next_action": next_action,
        "data": {
            "data_status": data_status,
            "missing_datasets": missing,
            "stale_datasets": stale,
        },
        "errors": [],
    }
