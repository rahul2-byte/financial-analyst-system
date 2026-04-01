from __future__ import annotations

from typing import Any

from app.core.graph.agent_map import AGENT_NODE_MAP
from app.core.graph.async_control import run_parallel_with_timeout
from app.core.node_resources import resources


def _task_sort_key(task: dict[str, Any]) -> tuple[int, str]:
    priority_map = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    return (priority_map.get(task.get("priority", "P3"), 3), str(task.get("task_id", "")))


async def autonomous_research_planner_node(state: dict[str, Any]) -> dict[str, Any]:
    ticker = state.get("goal", {}).get("ticker")
    query = state.get("user_query", "")

    tasks = list(state.get("replanned_tasks", []))
    if not tasks:
        tasks = [
            {
                "task_id": "fundamental_analysis",
                "agent": "fundamental_analysis",
                "priority": "P0",
                "parameters": {"ticker": ticker, "query": query},
            },
            {
                "task_id": "sentiment_analysis",
                "agent": "sentiment_analysis",
                "priority": "P1",
                "parameters": {"ticker": ticker, "query": query},
            },
            {
                "task_id": "macro_analysis",
                "agent": "macro_analysis",
                "priority": "P1",
                "parameters": {"ticker": ticker, "query": query},
            },
        ]

    tasks = sorted(tasks, key=_task_sort_key)
    return {
        "tasks": tasks,
        "force_replan": False,
        "replanned_tasks": [],
        "status": "success",
        "reasoning": "Built prioritized research tasks from goal and hypotheses.",
        "confidence_score": float(state.get("confidence_score", 0.6)),
        "next_action": "run_research_exec",
        "data": {"tasks": tasks},
        "errors": [],
    }


async def autonomous_research_execution_node(state: dict[str, Any]) -> dict[str, Any]:
    tasks = sorted(state.get("tasks", []), key=_task_sort_key)
    coroutines = []
    agent_order: list[str] = []

    for task in tasks:
        agent = task.get("agent")
        node_fn = AGENT_NODE_MAP.get(agent)
        if node_fn is None:
            continue
        agent_order.append(agent)
        modified_state = {
            **state,
            "current_step": {"parameters": task.get("parameters", {})},
        }
        coroutines.append(node_fn(modified_state, resources))

    results: dict[str, Any] = {}
    tool_registry: list[dict[str, Any]] = list(state.get("tool_registry", []))
    errors: list[str] = []

    completed, timeout_errors = await run_parallel_with_timeout(
        coroutines,
        task_timeout_s=float(state.get("timeouts", {}).get("task_timeout_s", 10.0)),
        stage_timeout_s=float(state.get("timeouts", {}).get("stage_timeout_s", 20.0)),
    )
    errors.extend(timeout_errors)

    for index, agent in enumerate(agent_order):
        result = completed[index] if index < len(completed) else None
        if result is None:
            errors.append(f"{agent}: no result")
            continue
        if isinstance(result, Exception):
            errors.append(f"{agent}: {result}")
            continue
        if not isinstance(result, dict):
            errors.append(f"{agent}: invalid response type")
            continue
        if result.get("errors"):
            errors.extend([f"{agent}: {e}" for e in result.get("errors", [])])
        if result.get("tool_registry"):
            for tool_entry in result.get("tool_registry", []):
                if isinstance(tool_entry, dict):
                    tool_registry.append(tool_entry)
        agent_outputs = result.get("agent_outputs", {})
        payload = agent_outputs.get(agent)
        if payload is None and isinstance(agent_outputs, dict) and len(agent_outputs) == 1:
            payload = next(iter(agent_outputs.values()))
        if payload is None:
            errors.append(f"{agent}: missing agent payload")
            continue
        results[agent] = payload if payload is not None else result.get("agent_outputs", {})

    return {
        "results": {**state.get("results", {}), **results},
        "tool_registry": tool_registry,
        "status": "partial" if errors else "success",
        "reasoning": "Executed selected research agents in parallel with timeout controls.",
        "confidence_score": float(state.get("confidence_score", 0.6)),
        "next_action": "run_synthesis",
        "data": {"results": results, "tool_registry_count": len(tool_registry)},
        "errors": errors,
    }
