from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from app.core.graph.graph_state import ResearchGraphState
from app.core.graph.legacy_routes import (
    route_after_discovery,
    route_after_error_handler,
    route_after_execution,
    route_after_planner,
    route_after_synthesis,
    route_after_validation,
    route_after_verification,
)
from app.core.graph.nodes.autonomous_data_nodes import (
    autonomous_data_checker_node,
    autonomous_data_fetch_node,
    autonomous_data_planner_node,
)
from app.core.graph.nodes.autonomous_goal_node import autonomous_goal_node
from app.core.graph.nodes.autonomous_quality_nodes import (
    autonomous_conflict_resolution_node,
    autonomous_critic_node,
    autonomous_reflection_node,
    autonomous_synthesis_node,
)
from app.core.graph.nodes.autonomous_research_nodes import (
    autonomous_research_execution_node,
    autonomous_research_planner_node,
)
from app.core.graph.nodes.autonomous_router_node import autonomous_router_node
from app.core.graph.nodes.autonomous_validation_node import autonomous_validation_node


def _route_after_router(state: ResearchGraphState) -> str:
    decision = state.get("router_decision")
    return decision if isinstance(decision, str) else "terminate_failure"


def _route_to_router(_state: ResearchGraphState) -> str:
    return "run_router"


def _route_after_data_check(state: ResearchGraphState) -> str:
    missing = state.get("data_check", {}).get("missing_datasets", [])
    stale = state.get("data_check", {}).get("stale_datasets", [])
    return "run_data_plan" if (missing or stale) else "run_router"


def _route_after_conflict(_state: ResearchGraphState) -> str:
    return "run_synthesis"


def _route_after_synthesis(_state: ResearchGraphState) -> str:
    return "run_critic"


def build_graph() -> Any:
    graph = StateGraph(ResearchGraphState)

    graph.add_node("router_node", autonomous_router_node)
    graph.add_node("goal_hypothesis_node", autonomous_goal_node)
    graph.add_node("data_checker_node", autonomous_data_checker_node)
    graph.add_node("data_planner_node", autonomous_data_planner_node)
    graph.add_node("data_fetch_node", autonomous_data_fetch_node)
    graph.add_node("research_planner_node", autonomous_research_planner_node)
    graph.add_node("research_execution_node", autonomous_research_execution_node)
    graph.add_node("synthesis_node", autonomous_synthesis_node)
    graph.add_node("critic_node", autonomous_critic_node)
    graph.add_node("reflection_node", autonomous_reflection_node)
    graph.add_node("conflict_resolution_node", autonomous_conflict_resolution_node)
    graph.add_node("validation_node", autonomous_validation_node)

    graph.set_entry_point("router_node")

    graph.add_conditional_edges(
        "router_node",
        _route_after_router,
        {
            "run_goal_hypothesis": "goal_hypothesis_node",
            "run_data_check": "data_checker_node",
            "run_data_plan": "data_planner_node",
            "run_data_fetch": "data_fetch_node",
            "run_research_plan": "research_planner_node",
            "run_research_exec": "research_execution_node",
            "run_synthesis": "synthesis_node",
            "run_critic": "critic_node",
            "run_reflection": "reflection_node",
            "run_conflict_resolution": "conflict_resolution_node",
            "run_validation": "validation_node",
            "terminate_success": END,
            "terminate_insufficient_data": END,
            "terminate_budget_exceeded": END,
            "terminate_failure": END,
        },
    )

    graph.add_conditional_edges("goal_hypothesis_node", _route_to_router, {"run_router": "router_node"})
    graph.add_conditional_edges("data_checker_node", _route_after_data_check, {
        "run_data_plan": "data_planner_node",
        "run_router": "router_node",
    })
    graph.add_conditional_edges("data_planner_node", _route_to_router, {"run_router": "router_node"})
    graph.add_conditional_edges("data_fetch_node", _route_to_router, {"run_router": "router_node"})
    graph.add_conditional_edges("research_planner_node", _route_to_router, {"run_router": "router_node"})
    graph.add_conditional_edges("research_execution_node", _route_to_router, {"run_router": "router_node"})
    graph.add_conditional_edges("critic_node", _route_to_router, {"run_router": "router_node"})
    graph.add_conditional_edges("reflection_node", _route_to_router, {"run_router": "router_node"})
    graph.add_conditional_edges("validation_node", _route_to_router, {"run_router": "router_node"})

    graph.add_conditional_edges(
        "conflict_resolution_node",
        _route_after_conflict,
        {"run_synthesis": "synthesis_node"},
    )
    graph.add_conditional_edges(
        "synthesis_node",
        _route_after_synthesis,
        {"run_critic": "critic_node"},
    )

    return graph.compile()


_cached_graph = None


def get_research_graph() -> Any:
    global _cached_graph
    if _cached_graph is None:
        _cached_graph = build_graph()
    return _cached_graph
