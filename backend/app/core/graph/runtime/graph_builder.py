from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from app.core.graph.graph_state import ResearchGraphState
from agents.financial.data.data_fetch_node import data_fetch_node
from agents.financial.data.data_check_node import data_check_node
from agents.financial.data.data_plan_node import data_plan_node
from agents.orchestration.goal_node import goal_node
from agents.quality.nodes import (
    conflict_resolution_node,
    critic_node,
    evaluator_node,
    synthesis_node,
)
from agents.financial.research.research_plan_node import research_plan_node
from agents.financial.research.research_execution_node import research_execution_node
from agents.orchestration.router_node import router_node
from agents.orchestration.validation_node import validation_node


def _route_after_router(state: ResearchGraphState) -> str:
    decision = state.get("router_decision")
    return decision if isinstance(decision, str) else "terminate_failure"


def _route_to_router(_state: ResearchGraphState) -> str:
    return "run_router"


def _route_after_data_check(state: ResearchGraphState) -> str:
    missing = state.get("data_check", {}).get("missing_datasets", [])
    stale = state.get("data_check", {}).get("stale_datasets", [])
    return "run_data_plan" if (missing or stale) else "run_router"


def _route_after_data_plan(_state: ResearchGraphState) -> str:
    return "run_data_fetch"


def _route_after_conflict(_state: ResearchGraphState) -> str:
    return "run_synthesis"


def _route_after_synthesis(_state: ResearchGraphState) -> str:
    return "run_critic"


def _route_after_validation(state: ResearchGraphState) -> str:
    return (
        "run_evaluator"
        if state.get("validation_passed", False)
        else "terminate_failure"
    )


def _route_after_evaluator(state: ResearchGraphState) -> str:
    return (
        "terminate_failure"
        if state.get("next_action") == "terminate_failure"
        else "run_router"
    )


def build_graph() -> Any:
    graph = StateGraph(ResearchGraphState)

    graph.add_node("router_node", router_node)
    graph.add_node("goal_node", goal_node)
    graph.add_node("data_check_node", data_check_node)
    graph.add_node("data_plan_node", data_plan_node)
    graph.add_node("data_fetch_node", data_fetch_node)
    graph.add_node("research_plan_node", research_plan_node)
    graph.add_node("research_execution_node", research_execution_node)
    graph.add_node("synthesis_node", synthesis_node)
    graph.add_node("critic_node", critic_node)
    graph.add_node("evaluator_node", evaluator_node)
    graph.add_node("conflict_resolution_node", conflict_resolution_node)
    graph.add_node("validation_node", validation_node)

    graph.set_entry_point("router_node")

    graph.add_conditional_edges(
        "router_node",
        _route_after_router,
        {
            "run_goal": "goal_node",
            "run_data_check": "data_check_node",
            "run_data_plan": "data_plan_node",
            "run_data_fetch": "data_fetch_node",
            "run_research_plan": "research_plan_node",
            "run_research_execution": "research_execution_node",
            "run_synthesis": "synthesis_node",
            "run_critic": "critic_node",
            "run_evaluator": "evaluator_node",
            "run_conflict_resolution": "conflict_resolution_node",
            "run_validation": "validation_node",
            "terminate_success": END,
            "terminate_awaiting_input": END,
            "terminate_insufficient_data": END,
            "terminate_budget_exceeded": END,
            "terminate_failure": END,
        },
    )

    graph.add_conditional_edges(
        "goal_node", _route_to_router, {"run_router": "router_node"}
    )
    graph.add_conditional_edges(
        "data_check_node",
        _route_after_data_check,
        {
            "run_data_plan": "data_plan_node",
            "run_router": "router_node",
        },
    )
    graph.add_conditional_edges(
        "data_plan_node",
        _route_after_data_plan,
        {"run_data_fetch": "data_fetch_node"},
    )
    graph.add_conditional_edges(
        "data_fetch_node", _route_to_router, {"run_router": "router_node"}
    )
    graph.add_conditional_edges(
        "research_plan_node", _route_to_router, {"run_router": "router_node"}
    )
    graph.add_conditional_edges(
        "research_execution_node", _route_to_router, {"run_router": "router_node"}
    )
    graph.add_conditional_edges(
        "critic_node", _route_to_router, {"run_router": "router_node"}
    )
    graph.add_conditional_edges(
        "validation_node",
        _route_after_validation,
        {"run_evaluator": "evaluator_node", "terminate_failure": END},
    )
    graph.add_conditional_edges(
        "evaluator_node",
        _route_after_evaluator,
        {"run_router": "router_node", "terminate_failure": END},
    )

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
