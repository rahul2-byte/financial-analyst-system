"""Execution-level orchestration node handler."""

import asyncio
import logging
from typing import Any, Dict, Set

from app.core.graph.agent_map import AGENT_NODE_MAP
from app.core.graph.graph_state import ResearchGraphState
from app.core.graph.scheduler import find_next_level, get_agent_name
from app.core.node_resources import NodeResources
from app.core.orchestration_schemas import ExecutionStep

logger = logging.getLogger(__name__)


async def execute_level_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Executes the next level of steps in parallel using stateless function nodes."""
    plan_data = state.get("plan")
    if not plan_data:
        return {"errors": ["No plan in state"]}

    execution_steps = [ExecutionStep(**s) for s in plan_data.get("execution_steps", [])]

    current_executed = state.get("executed_steps", [])
    executed_step_ids = {s.get("step_number") for s in current_executed}

    next_level = find_next_level(execution_steps, executed_step_ids)

    if not next_level:
        if len(current_executed) < len(execution_steps):
            return {"errors": ["No steps ready to execute - possible circular dependency"]}
        return {
            "agent_outputs": state.get("agent_outputs", {}),
            "executed_steps": current_executed,
        }

    agent_tasks = []
    for step in next_level:
        agent_name = get_agent_name(step)
        node_func = AGENT_NODE_MAP.get(agent_name)

        if not node_func:
            logger.error(f"Agent {agent_name} not found in node map")
            return {"errors": [f"Agent {agent_name} not found"]}

        modified_state = {**state, "current_step": step.model_dump()}
        agent_tasks.append(node_func(modified_state, resources=resources))

    results = (
        await asyncio.gather(*agent_tasks, return_exceptions=True) if agent_tasks else []
    )

    new_agent_outputs = dict(state.get("agent_outputs", {}))
    new_executed_steps = list(current_executed)
    all_errors = []
    all_tool_results = []

    for step, result in zip(next_level, results):
        agent_name = get_agent_name(step)
        if isinstance(result, Exception):
            logger.error(f"Step {step.step_number} failed: {result}")
            all_errors.append(f"Step {step.step_number} ({agent_name}) failed: {result}")
            new_agent_outputs[str(step.step_number)] = f"Error: {str(result)}"
            new_executed_steps.append(
                {"step_number": step.step_number, "agent": agent_name, "status": "failed"}
            )
        elif isinstance(result, dict) and "errors" in result:
            step_errors = result.get("errors", [])
            all_errors.extend(
                [f"Step {step.step_number} ({agent_name}) failed: {err}" for err in step_errors]
            )
            new_agent_outputs[str(step.step_number)] = "Error"
            new_executed_steps.append(
                {"step_number": step.step_number, "agent": agent_name, "status": "failed"}
            )
        elif isinstance(result, dict) and result.get("agent_outputs"):
            outputs = result["agent_outputs"]
            # Fix: Deterministic lookup. Prefer agent_name, then step_number as string.
            # Avoid next(iter()) which is non-deterministic.
            output_val = outputs.get(agent_name) or outputs.get(str(step.step_number))
            
            if output_val is None and outputs:
                # If still not found, and there are outputs, we have a mismatch.
                # Log it and take the first key, but this should be avoided by nodes using build_node_success.
                logger.warning(f"Output for {agent_name} (step {step.step_number}) not found in agent_outputs. Available keys: {list(outputs.keys())}")
                output_val = next(iter(outputs.values()))

            new_agent_outputs[str(step.step_number)] = output_val
            all_tool_results.extend(result.get("tool_registry", []))
            new_executed_steps.append(
                {
                    "step_number": step.step_number,
                    "agent": agent_name,
                    "status": "completed",
                }
            )

    if all_errors:
        failed_steps = [
            step.get("step_number")
            for step in new_executed_steps
            if step.get("status") == "failed"
        ]
        return {
            "errors": all_errors,
            "failed_node": "execute_level_node",
            "failed_step_number": failed_steps[0] if failed_steps else None,
            "agent_outputs": new_agent_outputs,
            "executed_steps": new_executed_steps,
            "tool_registry": all_tool_results,
        }

    return {
        "agent_outputs": new_agent_outputs,
        "executed_steps": new_executed_steps,
        "tool_registry": all_tool_results,
    }
