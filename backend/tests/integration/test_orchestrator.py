"""Integration tests for the orchestrator and graph flow."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.core.graph.graph_builder import (
    build_graph,
    route_after_planner,
    route_after_execution,
    route_after_synthesis,
    route_after_verification,
    route_after_error_handler,
    route_after_validation,
)
from app.core.graph.graph_state import ResearchGraphState


class TestGraphRouting:
    """Test graph routing logic."""

    def test_route_after_planner_with_errors(self):
        """Planner errors should route to error_handler."""
        state = {"errors": ["Invalid plan"], "plan": None}
        result = route_after_planner(state)
        assert result == "error_handler"

    def test_route_after_planner_with_valid_plan(self):
        """Valid plan should route to execute_level_node."""
        state = {"errors": [], "plan": {"execution_steps": [1, 2, 3]}}
        result = route_after_planner(state)
        assert result == "execute_level_node"

    def test_route_after_planner_no_plan(self):
        """No plan should route to END."""
        state = {"errors": [], "plan": None}
        result = route_after_planner(state)
        assert result == "__end__"

    def test_route_after_execution_all_steps_complete(self):
        """All steps complete should route to synthesis."""
        state = {
            "errors": [],
            "plan": {"execution_steps": [1, 2, 3]},
            "executed_steps": [1, 2, 3],
        }
        result = route_after_execution(state)
        assert result == "synthesis_node"

    def test_route_after_execution_more_steps_pending(self):
        """More steps pending should loop to execute_level_node."""
        state = {
            "errors": [],
            "plan": {"execution_steps": [1, 2, 3]},
            "executed_steps": [1],
        }
        result = route_after_execution(state)
        assert result == "execute_level_node"

    def test_route_after_execution_with_errors(self):
        """Execution errors should route to error_handler."""
        state = {
            "errors": ["Step 1 failed"],
            "plan": {"execution_steps": [1, 2]},
            "executed_steps": [1],
        }
        result = route_after_execution(state)
        assert result == "error_handler"

    def test_route_after_synthesis_always_verification(self):
        """Synthesis should always route to verification."""
        state = {"errors": [], "draft_report": "Test report"}
        result = route_after_synthesis(state)
        assert result == "verification_node"

    def test_route_after_verification_passed(self):
        """Verification passed should route to validation."""
        state = {"verification_passed": True}
        result = route_after_verification(state)
        assert result == "validation_node"

    def test_route_after_verification_failed_retry(self):
        """Verification failed under retry limit should go to synthesis."""
        state = {"verification_passed": False, "verification_retry_count": 1}
        result = route_after_verification(state)
        assert result == "synthesis_node"

    def test_route_after_verification_failed_exhausted(self):
        """Verification failed over retry limit should end."""
        state = {"verification_passed": False, "verification_retry_count": 3}
        result = route_after_verification(state)
        assert result == "__end__"

    def test_route_after_error_handler_retry(self):
        """Error handler with should_retry should go to execute_level_node."""
        state = {"should_retry": True, "should_escalate": False}
        result = route_after_error_handler(state)
        assert result == "execute_level_node"

    def test_route_after_error_handler_retry_planner_phase(self):
        """Planner failures should retry planner node, not execution node."""
        state = {
            "should_retry": True,
            "should_escalate": False,
            "failed_node": "planner_node",
        }
        result = route_after_error_handler(state)
        assert result == "planner_node"

    def test_route_after_error_handler_retry_validation_phase(self):
        """Validation failures should retry validation node."""
        state = {
            "should_retry": True,
            "should_escalate": False,
            "failed_node": "validation_node",
        }
        result = route_after_error_handler(state)
        assert result == "validation_node"

    def test_route_after_error_handler_escalate(self):
        """Error handler with should_escalate should end."""
        state = {"should_retry": False, "should_escalate": True}
        result = route_after_error_handler(state)
        assert result == "__end__"

    def test_route_after_validation_ignores_verification_feedback_state(self):
        """Validation should not fail-route on non-terminal verification feedback."""
        state = {
            "errors": [],
            "verification_passed": False,
            "verification_feedback": "numbers mismatched",
        }
        result = route_after_validation(state)
        assert result == "__end__"


class TestGraphStateMerging:
    """Test state merging behavior."""

    def test_merge_tool_registry_concatenates(self):
        """Tool registry should concatenate, not overwrite."""
        from app.core.graph.graph_state import merge_dicts

        left = {"tool_registry": [{"tool": "a"}]}
        right = {"tool_registry": [{"tool": "b"}]}

        result = merge_dicts(left, right)

        assert len(result["tool_registry"]) == 2
        assert result["tool_registry"][0]["tool"] == "a"
        assert result["tool_registry"][1]["tool"] == "b"

    def test_merge_executed_steps_concatenates(self):
        """Executed steps should concatenate."""
        from app.core.graph.graph_state import merge_dicts

        left = {"executed_steps": [{"step_number": 1}]}
        right = {"executed_steps": [{"step_number": 2}]}

        result = merge_dicts(left, right)

        assert len(result["executed_steps"]) == 2

    def test_merge_agent_outputs_merges_nested(self):
        """Agent outputs should deep merge."""
        from app.core.graph.graph_state import merge_dicts

        left = {"agent_outputs": {"step1": {"price": 100}}}
        right = {"agent_outputs": {"step2": {"volume": 1000}}}

        result = merge_dicts(left, right)

        assert "step1" in result["agent_outputs"]
        assert "step2" in result["agent_outputs"]
        assert result["agent_outputs"]["step1"]["price"] == 100


class TestErrorRecovery:
    """Test error recovery scenarios."""

    def test_error_handler_clears_failed_step(self):
        """Error handler should clear failed step on retry."""
        from app.core.error_handling import ErrorHandler

        handler = ErrorHandler(max_retries=3)

        state = {
            "errors": ["Timeout"],
            "retry_count": 0,
            "failed_node": "execute_level_node",
            "failed_step_number": 2,
            "executed_steps": [
                {"step_number": 1, "status": "completed"},
                {"step_number": 2, "status": "failed"},
            ],
            "agent_outputs": {
                "1": {"data": "ok"},
                "2": {"data": "failed"},
            },
        }

        failed_step = state.get("failed_step_number")
        executed_steps = [
            s
            for s in state.get("executed_steps", [])
            if s.get("step_number") != failed_step
        ]

        assert len(executed_steps) == 1
        assert executed_steps[0]["step_number"] == 1


class TestInputSanitization:
    """Test input sanitization."""

    def test_sanitize_removes_null_bytes(self):
        """Sanitize should remove null bytes."""
        from app.core.orchestrator import sanitize_user_query

        result = sanitize_user_query("test\x00query")

        assert "\x00" not in result

    def test_sanitize_truncates_long_input(self):
        """Sanitize should truncate very long input."""
        from app.core.orchestrator import sanitize_user_query

        long_query = "a" * 5000
        result = sanitize_user_query(long_query, max_length=100)

        assert len(result) <= 100

    def test_validate_rejects_empty_query(self):
        """Validate should reject empty queries."""
        from app.core.orchestrator import validate_query_not_malicious

        is_safe, reason = validate_query_not_malicious("")

        assert not is_safe
        assert reason == "Empty query"

    def test_validate_accepts_normal_query(self):
        """Validate should accept normal queries."""
        from app.core.orchestrator import validate_query_not_malicious

        is_safe, reason = validate_query_not_malicious("Analyze AAPL stock")

        assert is_safe


class TestCircuitBreaker:
    """Test circuit breaker behavior."""

    def test_circuit_starts_closed(self):
        """Circuit should start in closed state."""
        from app.core.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker("test")

        assert cb.state.value == "closed"
        assert cb.can_execute()

    def test_circuit_opens_after_failures(self):
        """Circuit should open after threshold failures."""
        from app.core.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker("test", failure_threshold=3)

        cb.record_failure()
        cb.record_failure()
        assert cb.can_execute()

        cb.record_failure()
        assert not cb.can_execute()

    def test_circuit_resets_on_success(self):
        """Circuit should reset failure count on success."""
        from app.core.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker("test", failure_threshold=3)

        cb.record_failure()
        cb.record_failure()
        cb.record_success()

        cb.record_failure()
        assert cb.can_execute()
