"""Research execution node."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agents.shared.utils import task_sort_key
from app.core.audit import build_node_audit_entry
from app.core.contracts.graph_node import finalize_node_output
from app.core.graph.agent_map import AGENT_NODE_MAP
from app.core.graph.async_control import run_parallel_with_timeout
from app.core.node_resources import resources
from app.core.observability import observe, opik_context
from app.core.research_plan_schemas import AgentExecutionInput, ResearchTaskSpec


def _stage_tasks(tasks: list[ResearchTaskSpec]) -> list[list[ResearchTaskSpec]]:
    remaining = {task.task_id: task for task in tasks}
    completed: set[str] = set()
    stages: list[list[ResearchTaskSpec]] = []

    while remaining:
        runnable = [
            task
            for task in remaining.values()
            if all(dependency in completed for dependency in task.depends_on)
        ]
        if not runnable:
            stages.append(
                sorted(
                    remaining.values(),
                    key=lambda task: task_sort_key(task.model_dump(mode="json")),
                )
            )
            break
        runnable = sorted(
            runnable,
            key=lambda task: task_sort_key(task.model_dump(mode="json")),
        )
        stages.append(runnable)
        for task in runnable:
            completed.add(task.agent)
            remaining.pop(task.task_id, None)
    return stages


def _resolve_execution_input(
    task: ResearchTaskSpec,
    state: dict[str, Any],
    results: dict[str, Any],
) -> dict[str, Any]:
    task_contexts = state.get("task_contexts", {})
    raw_input = task_contexts.get(task.task_id)
    if raw_input is None:
        raw_input = task.parameters.get("execution_input")
    if raw_input is None:
        return {}
    execution_input = AgentExecutionInput.model_validate(raw_input)
    dependency_results = {
        dependency: results[dependency]
        for dependency in task.depends_on
        if dependency in results
    }
    if dependency_results:
        execution_input.evidence_bundle.dependency_results = dependency_results
    return execution_input.model_dump(mode="json")


@observe(name="Research:Execution", as_type="span")
async def research_execution_node(state: dict[str, Any]) -> dict[str, Any]:
    parsed_tasks: list[ResearchTaskSpec] = []
    validation_errors: list[str] = []
    for raw_task in state.get("tasks", []):
        try:
            parsed_tasks.append(ResearchTaskSpec.model_validate(raw_task))
        except Exception as exc:  # noqa: BLE001
            validation_errors.append(f"invalid_task_contract: {exc}")

    if validation_errors:
        return finalize_node_output(
            "research_execution_node",
            {
                "status": "failure",
                "reasoning": "Research execution aborted due to invalid task contracts.",
                "confidence_score": float(state.get("confidence_score", 0.0)),
                "next_action": "terminate_failure",
                "data": {},
                "errors": validation_errors,
            },
        )

    staged_tasks = _stage_tasks(parsed_tasks)
    results: dict[str, Any] = {
        agent: payload
        for agent, payload in dict(state.get("results", {})).items()
        if isinstance(payload, dict)
    }
    tool_registry: list[dict[str, Any]] = list(state.get("tool_registry", []))
    errors: list[str] = []
    hard_errors: list[str] = []
    required_agents = set(
        state.get("required_agents", state.get("approved_agents", []))
    )
    blocked_tasks_summary: list[dict[str, Any]] = []
    runnable_tasks_by_stage: list[dict[str, Any]] = []
    timeout_error_count = 0
    stage_diagnostics: list[dict[str, Any]] = []

    for stage in staged_tasks:
        stage_entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage_size": len(stage),
            "stage_task_ids": [task.task_id for task in stage],
            "blocked_task_ids": [],
            "runnable_task_ids": [],
            "agents_executed": [],
            "agents_with_errors": [],
        }
        blocked_tasks = [
            task
            for task in stage
            if any(dependency not in results for dependency in task.depends_on)
        ]
        stage_entry["blocked_task_ids"] = [task.task_id for task in blocked_tasks]
        if blocked_tasks:
            blocked_tasks_summary.extend(
                [
                    {
                        "task_id": task.task_id,
                        "agent": task.agent,
                        "depends_on": list(task.depends_on),
                    }
                    for task in blocked_tasks
                ]
            )
            for task in blocked_tasks:
                message = (
                    f"{task.agent}: dependency_unmet: {', '.join(task.depends_on)}"
                )
                errors.append(message)
                if task.agent in required_agents:
                    hard_errors.append(message)
            if hard_errors:
                break

        runnable_tasks = [t for t in stage if t not in blocked_tasks]
        stage_entry["runnable_task_ids"] = [task.task_id for task in runnable_tasks]
        if not runnable_tasks:
            stage_diagnostics.append(stage_entry)
            continue

        runnable_tasks_by_stage.append(
            {
                "stage_index": len(runnable_tasks_by_stage) + 1,
                "task_ids": [task.task_id for task in runnable_tasks],
                "agents": [task.agent for task in runnable_tasks],
            }
        )

        coroutines = []
        agent_order: list[str] = []
        for task in runnable_tasks:
            node_fn = AGENT_NODE_MAP.get(task.agent)
            if node_fn is None:
                message = f"{task.agent}: no registered node"
                errors.append(message)
                if task.agent in required_agents:
                    hard_errors.append(message)
                continue
            execution_input = _resolve_execution_input(task, state, results)
            stage_entry["agents_executed"].append(
                {
                    "agent": task.agent,
                    "task_id": task.task_id,
                    "execution_input_present": bool(execution_input),
                }
            )
            modified_state = {
                **state,
                "results": results,
                "current_step": {
                    "parameters": (
                        {"execution_input": execution_input}
                        if execution_input
                        else dict(task.parameters)
                    )
                },
            }
            coroutines.append(node_fn(modified_state, resources))
            agent_order.append(task.agent)

        if not coroutines:
            continue

        completed, timeout_errors = await run_parallel_with_timeout(
            coroutines,
            task_timeout_s=state.get("timeouts", {}).get("task_timeout_s"),
            stage_timeout_s=state.get("timeouts", {}).get("stage_timeout_s"),
        )
        errors.extend(timeout_errors)
        timeout_error_count += len(timeout_errors)

        for index, agent in enumerate(agent_order):
            result = completed[index] if index < len(completed) else None
            if result is None:
                message = f"{agent}: no result"
                errors.append(message)
                stage_entry["agents_with_errors"].append(
                    {"agent": agent, "error": "no result"}
                )
                if agent in required_agents:
                    hard_errors.append(message)
                continue
            if isinstance(result, Exception):
                message = f"{agent}: {result}"
                errors.append(message)
                stage_entry["agents_with_errors"].append(
                    {"agent": agent, "error": str(result)}
                )
                if agent in required_agents:
                    hard_errors.append(message)
                continue
            if not isinstance(result, dict):
                message = f"{agent}: invalid response type"
                errors.append(message)
                stage_entry["agents_with_errors"].append(
                    {"agent": agent, "error": "invalid response type"}
                )
                if agent in required_agents:
                    hard_errors.append(message)
                continue
            if result.get("errors"):
                agent_errors = [
                    (
                        f"Required agent '{agent}' error: {error}"
                        if agent in required_agents
                        else f"{agent}: {error}"
                    )
                    for error in result.get("errors", [])
                ]
                errors.extend(agent_errors)
                stage_entry["agents_with_errors"].append(
                    {
                        "agent": agent,
                        "error_count": len(agent_errors),
                        "errors": agent_errors[:3],
                    }
                )
                if agent in required_agents:
                    hard_errors.extend(agent_errors)
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
                is_req = agent in required_agents
                message = f"{'Required agent' if is_req else 'Agent'} '{agent}' produced no payload"
                errors.append(message)
                stage_entry["agents_with_errors"].append(
                    {"agent": agent, "error": "missing payload"}
                )
                if is_req:
                    hard_errors.append(message)
                continue
            if not isinstance(payload, dict):
                is_req = agent in required_agents
                message = f"{'Required agent' if is_req else 'Agent'} '{agent}' produced invalid payload"
                errors.append(message)
                stage_entry["agents_with_errors"].append(
                    {"agent": agent, "error": "invalid payload"}
                )
                if is_req:
                    hard_errors.append(message)
                continue
            results[agent] = payload

        stage_diagnostics.append(stage_entry)

        if hard_errors:
            break

    status = "success"
    if hard_errors:
        status = "failure"
    elif errors:
        status = "partial"

    opik_context.update_current_span(
        metadata={
            "status": status,
            "tasks_executed": len(results),
            "tool_registry_count": len(tool_registry),
        }
    )

    payload = {
        "results": results,
        "tool_registry": tool_registry,
        "status": status,
        "reasoning": f"Executed selected research agents. Status: {status}.",
        "confidence_score": float(state.get("confidence_score", 0.6)),
        "next_action": "terminate_failure" if status == "failure" else "run_synthesis",
        "data": {"results": results, "tool_registry_count": len(tool_registry)},
        "errors": errors,
    }

    audit = build_node_audit_entry("research_execution_node", state, payload)

    agent_outcomes = {}
    for task in parsed_tasks:
        agent = task.agent
        if agent in results:
            result_data = results[agent]

            agent_status = result_data.get("status", "ok")
            findings = result_data.get("findings", [])
            claims = result_data.get("claims", [])

            preview_parts = []
            if findings:
                preview_parts.append(f"{len(findings)} findings")
            if claims:
                preview_parts.append(f"{len(claims)} claims")

            analysis_text = (
                ", ".join(preview_parts) if preview_parts else "No findings or claims"
            )

            agent_outcomes[agent] = {
                "status": agent_status,
                "has_errors": any(
                    e.startswith(f"{agent}:")
                    or e.startswith(f"Required agent '{agent}'")
                    for e in errors
                ),
                "result_preview": analysis_text,
            }
        elif any(
            e.startswith(f"{agent}:") or e.startswith(f"Required agent '{agent}'")
            for e in errors
        ):
            agent_outcomes[agent] = {
                "status": "failure",
                "has_errors": True,
                "result_preview": "",
            }
        else:
            agent_outcomes[agent] = {
                "status": "skipped",
                "has_errors": False,
                "result_preview": "",
            }

    audit["decision_summary"] = {
        "stages_executed": len(staged_tasks),
        "runnable_tasks_by_stage": runnable_tasks_by_stage,
        "stage_diagnostics": stage_diagnostics,
        "blocked_tasks": blocked_tasks_summary,
        "timeout_error_count": timeout_error_count,
        "hard_errors_count": len(hard_errors),
        "validation_errors": validation_errors,
        "agent_outcomes": agent_outcomes,
    }
    payload["data"]["audit"] = audit

    return finalize_node_output("research_execution_node", payload)
