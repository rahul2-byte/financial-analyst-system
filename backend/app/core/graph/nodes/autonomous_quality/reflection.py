from __future__ import annotations

from typing import Any

from app.core.contracts.graph_node import finalize_node_output


async def autonomous_reflection_node(state: dict[str, Any]) -> dict[str, Any]:
    retry_counts = dict(state.get("retry_count_by_domain", {}))
    retry_counts["research"] = retry_counts.get("research", 0) + 1

    tasks = list(state.get("tasks", []))
    reprioritized: list[dict[str, Any]] = []
    for task in tasks:
        updated_task = dict(task)
        if updated_task.get("priority") == "P1":
            updated_task["priority"] = "P0"
        reprioritized.append(updated_task)

    payload = {
        "retry_count_by_domain": retry_counts,
        "tasks": [],
        "replanned_tasks": reprioritized,
        "critic_decision": None,
        "force_replan": True,
        "results": {
            **state.get("results", {}),
            "reflection": {
                "root_cause": "low_evidence_or_conflict",
                "strategy_update": "promoted P1 tasks to P0 for stronger evidence",
            },
        },
        "status": "success",
        "reasoning": "Updated strategy and task priorities for the next iteration.",
        "confidence_score": float(state.get("confidence_score", 0.0)),
        "next_action": "run_research_plan",
        "data": {"tasks": [], "replanned_tasks": reprioritized},
        "errors": [],
    }
    return finalize_node_output("autonomous_reflection_node", payload)
