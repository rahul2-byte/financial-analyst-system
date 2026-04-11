"""Research execution node."""

from __future__ import annotations

from typing import Any

from app.core.contracts.graph_node import finalize_node_output
from app.core.graph.agent_map import AGENT_NODE_MAP
from app.core.graph.async_control import run_parallel_with_timeout
from app.core.node_resources import resources
from agents.shared.utils import task_sort_key


async def research_execution_node(state: dict[str, Any]) -> dict[str, Any]:
    tasks = sorted(state.get("tasks", []), key=task_sort_key)
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
        task_timeout_s=float(state.get("timeouts", {}).get("task_timeout_s", 30.0)),
        stage_timeout_s=float(state.get("timeouts", {}).get("stage_timeout_s", 30.0)),
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
        if (
            payload is None
            and isinstance(agent_outputs, dict)
            and len(agent_outputs) == 1
        ):
            payload = next(iter(agent_outputs.values()))
        if payload is None:
            errors.append(f"{agent}: missing agent payload")
            continue
        results[agent] = (
            payload if payload is not None else result.get("agent_outputs", {})
        )

    payload = {
        "results": {**state.get("results", {}), **results},
        "tool_registry": tool_registry,
        "status": "partial" if errors else "success",
        "reasoning": "Executed selected research agents in parallel with timeout controls.",
        "confidence_score": float(state.get("confidence_score", 0.6)),
        "next_action": "run_synthesis",
        "data": {"results": results, "tool_registry_count": len(tool_registry)},
        "errors": errors,
    }
    return finalize_node_output("research_execution_node", payload)
