import logging
from typing import Any

from langgraph.graph import StateGraph, END

from app.core.graph_state import ResearchGraphState
from app.core.graph_nodes import (
    planner_node,
    execute_level_node,
    synthesis_node,
    verification_node,
    validation_node,
)
from app.core.error_handler import error_handler_node
from agents.orchestration.schemas import PlannerResponseMode

logger = logging.getLogger(__name__)


def route_after_planner(state: ResearchGraphState) -> str:
    """Route after planner node based on response mode."""
    plan = state.get("plan")
    if not plan:
        logger.warning("No plan found in state, ending graph")
        return END

    response_mode = plan.get("response_mode", PlannerResponseMode.EXECUTE_PLAN)

    if response_mode != PlannerResponseMode.EXECUTE_PLAN:
        logger.info(f"Response mode is '{response_mode}', ending graph")
        return END

    logger.info("Response mode is 'execute_plan', routing to execute_level_node")
    return "execute_level_node"


def route_after_execution(state: ResearchGraphState) -> str:
    """Route after execution node - loop if more steps, else go to synthesis."""
    plan = state.get("plan")
    executed_steps = state.get("executed_steps", [])

    if not plan:
        logger.warning("No plan found in state, ending graph")
        return END

    execution_steps = plan.get("execution_steps", [])
    total_steps = len(execution_steps)
    executed_count = len(executed_steps)

    if executed_count >= total_steps:
        logger.info(f"All {executed_count} steps executed, routing to synthesis_node")
        return "synthesis_node"

    logger.info(
        f"Executed {executed_count}/{total_steps} steps, looping to execute_level_node"
    )
    return "execute_level_node"


def route_after_verification(state: ResearchGraphState) -> str:
    """Route after verification node based on validity and retry count."""
    verification_passed = state.get("verification_passed", False)
    verification_retry_count = state.get("verification_retry_count", 0)

    if verification_passed:
        logger.info("Verification passed, routing to validation_node")
        return "validation_node"

    if verification_retry_count < 3:
        logger.warning(
            f"Verification failed (retry {verification_retry_count}/3), routing to synthesis_node"
        )
        return "synthesis_node"

    logger.error("Verification failed after 3 retries, ending graph")
    return END


def route_after_validation(state: ResearchGraphState) -> str:
    """Route after validation node - always end."""
    logger.info("Validation complete, ending graph")
    return END


def build_enhanced_graph() -> Any:
    """Build the enhanced StateGraph with all improvements."""
    logger.info("Building Enhanced StateGraph v2")

    graph = StateGraph(ResearchGraphState)

    logger.info("Adding nodes to graph")
    graph.add_node("planner_node", planner_node)
    graph.add_node("execute_level_node", execute_level_node)
    graph.add_node("synthesis_node", synthesis_node)
    graph.add_node("verification_node", verification_node)
    graph.add_node("validation_node", validation_node)
    graph.add_node("error_handler_node", error_handler_node)

    logger.info("Adding start edge to planner_node")
    graph.add_edge("__start__", "planner_node")

    logger.info("Adding conditional edges from planner_node")
    graph.add_conditional_edges(
        "planner_node",
        route_after_planner,
        {
            "execute_level_node": "execute_level_node",
            END: END,
        },
    )

    logger.info("Adding conditional edges from execute_level_node")
    graph.add_conditional_edges(
        "execute_level_node",
        route_after_execution,
        {
            "synthesis_node": "synthesis_node",
            "execute_level_node": "execute_level_node",
        },
    )

    logger.info("Adding edge from synthesis_node to verification_node")
    graph.add_edge("synthesis_node", "verification_node")

    logger.info("Adding conditional edges from verification_node")
    graph.add_conditional_edges(
        "verification_node",
        route_after_verification,
        {
            "validation_node": "validation_node",
            "synthesis_node": "synthesis_node",
            END: END,
        },
    )

    logger.info("Adding conditional edges from validation_node")
    graph.add_conditional_edges(
        "validation_node",
        route_after_validation,
        {
            END: END,
        },
    )

    logger.info("Compiling graph")
    compiled_graph = graph.compile()

    logger.info("Enhanced StateGraph v2 compilation complete")
    return compiled_graph


enhanced_research_graph = build_enhanced_graph()
