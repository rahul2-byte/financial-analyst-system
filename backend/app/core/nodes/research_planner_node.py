from __future__ import annotations

from typing import Any


async def research_planner_node(state: dict[str, Any]) -> dict[str, Any]:
    tasks = state.get("tasks", [])
    if not tasks:
        tasks = [
            {"task_id": "fundamental", "agent": "fundamental", "priority": "P0"},
            {"task_id": "sentiment", "agent": "sentiment", "priority": "P1"},
            {"task_id": "macro", "agent": "macro", "priority": "P1"},
        ]

    return {
        "status": "success",
        "reasoning": "Created prioritized research tasks from available data and hypotheses.",
        "confidence_score": float(state.get("confidence_score", 0.65)),
        "next_action": "run_research_exec",
        "data": {"tasks": tasks},
        "tasks": tasks,
        "errors": [],
    }
