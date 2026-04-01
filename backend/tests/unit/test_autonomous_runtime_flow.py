import pytest

from app.core.graph.graph_builder import get_research_graph


@pytest.mark.asyncio
async def test_runtime_graph_reaches_terminal_state_without_recursion_error() -> None:
    graph = get_research_graph()

    initial_state = {
        "user_query": "Is AAPL a good trade?",
        "conversation_history": [],
        "plan": None,
        "executed_steps": [],
        "agent_outputs": {},
        "tool_registry": [],
        "draft_report": None,
        "final_report": None,
        "synthesis_retry_count": 0,
        "verification_retry_count": 0,
        "verification_passed": False,
        "verification_feedback": None,
        "data_manifest": None,
        "conflict_record": None,
        "conflict_iteration_count": 0,
        "status": None,
        "errors": [],
        "retry_count": 0,
        "should_retry": False,
        "should_escalate": False,
        "failed_node": None,
        "failed_step_number": None,
        "current_step": None,
        "selected_agents": [],
        "goal": None,
        "hypotheses": [],
        "data_status": {},
        "data_plan": [],
        "tasks": [],
        "results": {},
        "synthesis_confidence": 0.0,
        "adjusted_confidence": 0.0,
        "smoothed_confidence": 0.0,
        "confidence_score": 0.0,
        "final_confidence": 0.0,
        "confidence_history": [],
        "confidence_components": {},
        "critic_decision": None,
        "router_decision": None,
        "iteration_count": 0,
        "retry_count_by_domain": {},
        "freshness_policy": {},
        "evidence_strength": 0.0,
        "execution_budget": {},
        "timeouts": {},
        "errors_detail": [],
        "history": [],
        "termination_reason": None,
        "final_output": None,
    }

    result = await graph.ainvoke(initial_state, {"recursion_limit": 40})

    assert result.get("final_output") is not None
    assert result["final_output"].get("decision") is not None
    assert result["final_output"].get("confidence_score") is not None
