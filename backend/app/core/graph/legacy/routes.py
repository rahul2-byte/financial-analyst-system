from __future__ import annotations

from langgraph.graph import END

from app.core.graph.graph_state import ResearchGraphState


def route_after_discovery(state: ResearchGraphState) -> str:
    manifest = state.get("data_manifest") or {}
    if not manifest.get("user_approved", False):
        return END
    datasets = manifest.get("datasets", [])
    if any(d.get("status") == "missing" for d in datasets):
        return "acquisition_subgraph"
    return "planner_node"


def route_after_planner(state: ResearchGraphState) -> str:
    if state.get("errors"):
        return "error_handler"
    if "plan" not in state:
        return "research_subgraph"
    if not state.get("plan"):
        return END
    return "execute_level_node"


def route_after_execution(state: ResearchGraphState) -> str:
    if state.get("errors"):
        return "error_handler"
    plan = state.get("plan") or {}
    total = len(plan.get("execution_steps", []))
    executed = len(state.get("executed_steps", []))
    if executed >= total:
        return "synthesis_node"
    return "execute_level_node"


def route_after_synthesis(_state: ResearchGraphState) -> str:
    return "verification_node"


def route_after_verification(state: ResearchGraphState) -> str:
    if state.get("verification_passed"):
        return "validation_node"
    retry_count = int(state.get("verification_retry_count", 0))
    if retry_count == 0:
        return "research_subgraph"
    if retry_count < 3:
        return "synthesis_node"
    return END


def route_after_error_handler(state: ResearchGraphState) -> str:
    if state.get("should_escalate"):
        return END
    if state.get("should_retry"):
        failed_node = state.get("failed_node")
        if failed_node == "planner_node":
            return "planner_node"
        if failed_node == "validation_node":
            return "validation_node"
        return "execute_level_node"
    return END


def route_after_validation(state: ResearchGraphState) -> str:
    if state.get("errors"):
        return "error_handler"
    return END
