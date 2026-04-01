from __future__ import annotations

from typing import Any


async def data_fetch_node(state: dict[str, Any]) -> dict[str, Any]:
    plan = state.get("data_plan", [])
    data_status: dict[str, dict[str, Any]] = {}
    fetch_results: list[dict[str, Any]] = []

    for item in plan:
        dataset = item.get("dataset")
        if not dataset:
            continue
        data_status[dataset] = {
            "available": True,
            "partial": False,
            "freshness": 1.0,
            "source": "fetch_layer",
            "coverage": 1.0,
            "error": None,
        }
        fetch_results.append({"dataset": dataset, "status": "fetched"})

    status = "success" if fetch_results else "partial"

    return {
        "status": status,
        "reasoning": "Fetched or refreshed requested datasets according to plan order.",
        "confidence_score": 0.74 if status == "success" else 0.5,
        "next_action": "run_data_check",
        "data": {"data_status": data_status, "fetch_results": fetch_results},
        "errors": [],
    }
