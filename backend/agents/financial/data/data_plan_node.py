"""Financial data plan node (graph runtime).

This node converts the output of `data_check_node` into an executable `data_plan`.

Inputs:
- `state['data_check']['missing_datasets']`: datasets that must be fetched.
- `state['data_check']['stale_datasets']`: datasets that should be refreshed.
- `state['timeframe_policy']`: per-dataset policy (period, expected points, etc.).

Output:
- `data_plan`: list of `{dataset, priority, action, requirements}` items.

Behavior contract:
The plan item shape is consumed by `data_fetch_node` and is covered by unit tests.
"""

from __future__ import annotations

from typing import Any

from app.core.audit import build_node_audit_entry
from app.core.contracts.graph_node import finalize_node_output
from app.core.observability import observe, opik_context


def _dataset_requirements(
    dataset: str, timeframe_policy: dict[str, Any]
) -> dict[str, Any]:
    return dict(timeframe_policy.get(dataset, {}))


def _build_data_plan_audit(
    state: dict[str, Any],
    payload: dict[str, Any],
    missing: list[str],
    stale: list[str],
    data_plan: list[dict[str, Any]],
) -> dict[str, Any]:
    audit = build_node_audit_entry("data_plan_node", state, payload)
    goal = state.get("goal") if isinstance(state.get("goal"), dict) else {}
    symbols = []
    ticker = goal.get("ticker")
    if isinstance(ticker, str) and ticker.strip():
        symbols.append(ticker.strip().upper())
    audit["decision_summary"] = {
        "missing_datasets": missing,
        "stale_datasets": stale,
        "plan_count": len(data_plan),
        "symbols": symbols,
        "next_action": payload.get("next_action"),
        "planned_operations": [
            {
                "dataset": str(item.get("dataset", "")),
                "action": str(item.get("action", "")),
                "priority": str(item.get("priority", "")),
            }
            for item in data_plan[:5]
        ],
    }
    return audit


@observe(name="Data:Plan", as_type="span")
async def data_plan_node(state: dict[str, Any]) -> dict[str, Any]:
    # Defensive narrowing: upstream state is `dict[str, Any]`.
    checker_raw = state.get("data_check")
    checker = checker_raw if isinstance(checker_raw, dict) else {}

    timeframe_raw = state.get("timeframe_policy")
    timeframe_policy = dict(timeframe_raw) if isinstance(timeframe_raw, dict) else {}

    missing_raw = checker.get("missing_datasets", [])
    stale_raw = checker.get("stale_datasets", [])
    missing = missing_raw if isinstance(missing_raw, list) else []
    stale = stale_raw if isinstance(stale_raw, list) else []

    data_plan: list[dict[str, Any]] = []
    for dataset in missing:
        data_plan.append(
            {
                "dataset": dataset,
                "priority": "P0",
                "action": "materialize",
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

    opik_context.update_current_span(
        metadata={
            "missing_count": len(missing),
            "stale_count": len(stale),
            "operations_count": len(data_plan),
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
    payload["data"]["audit"] = _build_data_plan_audit(
        state, payload, missing, stale, data_plan
    )
    return finalize_node_output("data_plan_node", payload)
