import pytest
from app.core.graph_builder import route_after_error_handler
from app.core.graph_state import ResearchGraphState


def test_route_after_error_handler_retry_routes_to_execute_level_node():
    """Test that should_retry=True routes to execute_level_node, not planner_node.
    
    This is critical to preserve executed_steps and agent_outputs state.
    """
    state: ResearchGraphState = {
        "user_query": "test query",
        "conversation_history": [],
        "plan": {"steps": []},
        "executed_steps": [{"step": 1, "status": "completed"}],
        "agent_outputs": {"agent1": "output"},
        "tool_registry": [],
        "draft_report": None,
        "final_report": None,
        "synthesis_retry_count": 0,
        "verification_retry_count": 0,
        "verification_passed": False,
        "errors": [],
        "retry_count": 0,
        "should_retry": True,
        "should_escalate": False,
    }

    result = route_after_error_handler(state)
    
    assert result == "execute_level_node", (
        f"Expected 'execute_level_node' to preserve state, but got '{result}'. "
        "Routing to 'planner_node' loses executed_steps and agent_outputs!"
    )


def test_route_after_error_handler_escalate_routes_to_end():
    """Test that should_escalate=True routes to END."""
    state: ResearchGraphState = {
        "user_query": "test query",
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
        "errors": ["critical error"],
        "retry_count": 0,
        "should_retry": False,
        "should_escalate": True,
    }

    result = route_after_error_handler(state)
    
    from langgraph.graph import END
    assert result == END


def test_route_after_error_handler_no_retry_or_escalate_routes_to_end():
    """Test that no retry or escalate routes to END."""
    state: ResearchGraphState = {
        "user_query": "test query",
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
        "errors": [],
        "retry_count": 0,
        "should_retry": False,
        "should_escalate": False,
    }

    result = route_after_error_handler(state)
    
    from langgraph.graph import END
    assert result == END
