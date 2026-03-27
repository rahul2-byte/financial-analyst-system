import pytest
from app.core.graph_builder import route_after_error_handler


class TestErrorRouting:
    """Tests that error handler routes to execute_level_node, not planner_node."""

    def test_should_retry_routes_to_execute_level(self):
        """When should_retry is True, should route to execute_level_node to preserve state."""
        state = {
            "should_retry": True,
            "should_escalate": False,
            "executed_steps": [{"step_number": 1, "agent": "test"}],
            "agent_outputs": {"1": "some data"},
            "errors": []
        }
        
        result = route_after_error_handler(state)
        
        # CRITICAL: Should route to execute_level_node, NOT planner_node
        # planner_node would lose all executed_steps and agent_outputs
        assert result == "execute_level_node", f"Expected execute_level_node but got {result}"
    
    def test_should_escalate_routes_to_end(self):
        """When should_escalate is True, should route to END."""
        state = {
            "should_retry": False,
            "should_escalate": True,
            "errors": ["critical error"]
        }
        
        result = route_after_error_handler(state)
        
        assert result == "__end__" or result == "END", f"Expected END but got {result}"
    
    def test_no_retry_no_escalate_routes_to_end(self):
        """When both flags are False, should route to END."""
        state = {
            "should_retry": False,
            "should_escalate": False,
            "errors": []
        }
        
        result = route_after_error_handler(state)
        
        assert result == "__end__" or result == "END"
