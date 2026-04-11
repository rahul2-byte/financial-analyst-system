"""Data planner node."""

from __future__ import annotations

from typing import Any
from app.core.contracts.graph_node import finalize_node_output


def _dataset_requirements(
    dataset: str, timeframe_policy: dict[str, Any]
) -> dict[str, Any]:
    return dict(timeframe_policy.get(dataset, {}))


async def data_plan_node(state: dict[str, Any]) -> dict[str, Any]:
    checker = state.get("data_check", {})
    timeframe_policy = dict(state.get("timeframe_policy", {}))
    missing = checker.get("missing_datasets", [])
    stale = checker.get("stale_datasets", [])

    data_plan: list[dict[str, Any]] = []
    for dataset in missing:
        data_plan.append(
            {
                "dataset": dataset,
                "priority": "P0",
                "action": "fetch",
                "requirements": _dataset_requirements(dataset, timeframe_policy),
            }
        )
    for dataset in stale:
        data_plan.append(
            {
                "dataset": dataset,
                "priority": "P1",
                "action": "refresh",
                "requirements": _dataset_requirements(dataset, timeframe_policy),
            }
        )

    payload = {
        "data_plan": data_plan,
        "status": "success",
        "reasoning": "Prioritized data operations: missing first, stale second.",
        "confidence_score": 0.7,
        "next_action": "run_data_fetch",
        "data": {"data_plan": data_plan},
        "errors": [],
    }
    return finalize_node_output("data_plan_node", payload)
