from __future__ import annotations

from typing import Any


async def data_planner_node(state: dict[str, Any]) -> dict[str, Any]:
    checker_output = state.get("checker_output", {})
    missing = checker_output.get("missing_datasets", [])
    stale = checker_output.get("stale_datasets", [])

    plan: list[dict[str, Any]] = []
    for dataset in missing:
        plan.append({"dataset": dataset, "priority": "P0", "action": "fetch"})
    for dataset in stale:
        plan.append({"dataset": dataset, "priority": "P1", "action": "refresh"})

    return {
        "status": "success",
        "reasoning": "Planned data operations by deterministic priority: missing before stale.",
        "confidence_score": 0.78,
        "next_action": "run_data_fetch",
        "data": {"data_plan": plan},
        "errors": [],
    }
