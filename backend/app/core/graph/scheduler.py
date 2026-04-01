"""Scheduling helpers for execution-level node orchestration."""

from typing import List, Set

from app.core.orchestration_schemas import ExecutionStep


def get_agent_name(step: ExecutionStep) -> str:
    """Extract normalized agent name from execution step."""
    if hasattr(step.target_agent, "value"):
        return str(step.target_agent.value)
    return str(step.target_agent)


def find_next_level(
    steps: List[ExecutionStep], executed_step_ids: Set[int]
) -> List[ExecutionStep]:
    """Find steps whose dependencies are satisfied and not yet executed."""
    return [
        step
        for step in steps
        if step.step_number not in executed_step_ids
        if all(dep in executed_step_ids for dep in step.dependencies)
    ]
