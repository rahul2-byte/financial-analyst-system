from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from app.core.graph_state import ResearchGraphState
from app.core.nodes.autonomous_validation_node import autonomous_validation_node
from app.core.nodes.conflict_resolution_node import conflict_resolution_node
from app.core.nodes.critic_node import critic_node
from app.core.nodes.data_checker_node import data_checker_node
from app.core.nodes.data_fetch_node import data_fetch_node
from app.core.nodes.data_planner_node import data_planner_node
from app.core.nodes.goal_hypothesis_node import goal_hypothesis_node
from app.core.nodes.reflection_node import reflection_node
from app.core.nodes.research_execution_node import research_execution_node
from app.core.nodes.research_planner_node import research_planner_node
from app.core.nodes.router_node import router_node
from app.core.nodes.synthesis_node import synthesis_node


def _route_after_router(state: ResearchGraphState) -> str:
    decision = state.get("router_decision")
    if isinstance(decision, str):
        return decision
    return "terminate_failure"


def _route_to_router(_state: ResearchGraphState) -> str:
    return "run_router"


def _route_after_conflict_resolution(_state: ResearchGraphState) -> str:
    return "run_synthesis"


def _route_after_synthesis(_state: ResearchGraphState) -> str:
    return "run_critic"


def build_graph() -> Any:
    graph = StateGraph(ResearchGraphState)

    graph.add_node("router_node", router_node)
    graph.add_node("goal_hypothesis_node", goal_hypothesis_node)
    graph.add_node("data_checker_node", data_checker_node)
    graph.add_node("data_planner_node", data_planner_node)
    graph.add_node("data_fetch_node", data_fetch_node)
    graph.add_node("research_planner_node", research_planner_node)
    graph.add_node("research_execution_node", research_execution_node)
    graph.add_node("synthesis_node", synthesis_node)
    graph.add_node("critic_node", critic_node)
    graph.add_node("reflection_node", reflection_node)
    graph.add_node("conflict_resolution_node", conflict_resolution_node)
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
    graph.add_conditional_edges("data_checker_node", _route_to_router, {"run_router": "router_node"})
    graph.add_conditional_edges("data_planner_node", _route_to_router, {"run_router": "router_node"})
    graph.add_conditional_edges("data_fetch_node", _route_to_router, {"run_router": "router_node"})
    graph.add_conditional_edges("research_planner_node", _route_to_router, {"run_router": "router_node"})
    graph.add_conditional_edges("research_execution_node", _route_to_router, {"run_router": "router_node"})
    graph.add_conditional_edges("critic_node", _route_to_router, {"run_router": "router_node"})
    graph.add_conditional_edges("reflection_node", _route_to_router, {"run_router": "router_node"})
    graph.add_conditional_edges("validation_node", _route_to_router, {"run_router": "router_node"})

    graph.add_conditional_edges(
        "conflict_resolution_node",
        _route_after_conflict_resolution,
        {"run_synthesis": "synthesis_node"},
    )
    graph.add_conditional_edges(
        "synthesis_node",
        _route_after_synthesis,
        {"run_critic": "critic_node"},
    )

    return graph.compile()


research_graph = build_graph()
