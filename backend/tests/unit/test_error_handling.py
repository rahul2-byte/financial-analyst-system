"""Tests for error handling system."""

import pytest
from app.core.error_handling import (
    ErrorSeverity,
    should_retry,
    get_error_severity,
    apply_backoff,
    ErrorContext,
    ErrorAction,
    ErrorHandler,
    MAX_RETRIES,
)


class TestShouldRetry:
    """Test should_retry function."""

    def test_timeout_error_is_retriable(self):
        """Timeout errors should be retriable."""
        assert should_retry("Connection timeout") is True

    def test_network_error_is_retriable(self):
        """Network errors should be retriable."""
        assert should_retry("Network connection failed") is True

    def test_rate_limit_is_retriable(self):
        """Rate limit errors should be retriable."""
        assert should_retry("Rate limit exceeded") is True

    def test_authentication_error_is_not_retriable(self):
        """Authentication errors should not be retriable."""
        assert should_retry("Authentication failed") is False

    def test_authorization_error_is_not_retriable(self):
        """Authorization errors should not be retriable."""
        assert should_retry("Authorization denied") is False

    def test_quota_exceeded_is_not_retriable(self):
        """Quota exceeded errors should not be retriable."""
        assert should_retry("Quota exceeded") is False


class TestGetErrorSeverity:
    """Test get_error_severity function."""

    def test_critical_error_classification(self):
        """Critical errors should be classified as CRITICAL."""
        severity = get_error_severity("Authentication failed")
        assert severity == ErrorSeverity.CRITICAL

    def test_retriable_error_classification(self):
        """Retriable errors should be classified as HIGH."""
        severity = get_error_severity("Connection timeout")
        assert severity == ErrorSeverity.HIGH

    def test_default_medium_classification(self):
        """Default errors should be classified as MEDIUM."""
        severity = get_error_severity("Something went wrong")
        assert severity == ErrorSeverity.MEDIUM


class TestApplyBackoff:
    """Test apply_backoff function."""

    @pytest.mark.asyncio
    async def test_backoff_timing(self):
        """Backoff should wait approximately 2^retry_count seconds."""
        import time

        start = time.time()
        await apply_backoff(0)  # 1 second expected
        elapsed = time.time() - start

        assert 0.5 <= elapsed <= 2.0


class TestErrorContext:
    """Test ErrorContext dataclass."""

    def test_error_context_creation(self):
        """ErrorContext should create correctly."""
        ctx = ErrorContext(
            errors=["error1", "error2"],
            retry_count=1,
            failed_node="planner_node",
            failed_step_number=2,
        )

        assert len(ctx.errors) == 2
        assert ctx.retry_count == 1
        assert ctx.failed_node == "planner_node"
        assert ctx.failed_step_number == 2


class TestErrorAction:
    """Test ErrorAction dataclass."""

    def test_error_action_defaults(self):
        """ErrorAction should have correct defaults."""
        action = ErrorAction()

        assert action.should_retry is False
        assert action.should_escalate is False
        assert action.new_retry_count == 0
        assert action.cleanup_steps is None


class TestErrorHandler:
    """Test ErrorHandler class."""

    def test_should_continue_within_retries(self):
        """Should continue when within retry limit."""
        handler = ErrorHandler(max_retries=3)

        result = handler.should_continue(["timeout error"], retry_count=1)

        assert result is True

    def test_should_continue_exceeds_retries(self):
        """Should not continue when exceeding retry limit."""
        handler = ErrorHandler(max_retries=3)

        result = handler.should_continue(["timeout error"], retry_count=3)

        assert result is False

    def test_should_continue_with_critical_error(self):
        """Should not continue with critical errors."""
        handler = ErrorHandler(max_retries=3)

        result = handler.should_continue(["authentication failed"], retry_count=0)

        assert result is False

    def test_decide_retry(self):
        """Should decide to retry when appropriate."""
        handler = ErrorHandler(max_retries=3)
        ctx = ErrorContext(
            errors=["timeout error"],
            retry_count=0,
        )

        action = handler.decide(ctx)

        assert action.should_retry is True
        assert action.should_escalate is False

    def test_decide_escalate_critical(self):
        """Should escalate on critical errors."""
        handler = ErrorHandler(max_retries=3)
        ctx = ErrorContext(
            errors=["authentication failed"],
            retry_count=0,
        )

        action = handler.decide(ctx)

        assert action.should_retry is False
        assert action.should_escalate is True

    def test_decide_escalate_max_retries(self):
        """Should escalate after max retries."""
        handler = ErrorHandler(max_retries=3)
        ctx = ErrorContext(
            errors=["timeout error"],
            retry_count=3,
        )

        action = handler.decide(ctx)

        assert action.should_retry is False
        assert action.should_escalate is True

    def test_create_cleanup_updates(self):
        """Should create correct cleanup updates."""
        handler = ErrorHandler()

        updates = handler.create_cleanup_updates(
            retry_count=1,
            failed_step_number=2,
            executed_steps=[
                {"step_number": 1, "data": "test1"},
                {"step_number": 2, "data": "test2"},
            ],
            agent_outputs={"1": "output1", "2": "output2"},
        )

        assert updates["retry_count"] == 1
        assert updates["errors"] == []
        assert updates["should_retry"] is True
        assert len(updates["executed_steps"]) == 1
        assert "2" not in updates["agent_outputs"]

    def test_create_cleanup_updates_no_step(self):
        """Should create cleanup without step filtering when no failed step."""
        handler = ErrorHandler()

        updates = handler.create_cleanup_updates(
            retry_count=1,
            failed_step_number=None,
            executed_steps=[{"step_number": 1}],
            agent_outputs={"1": "output1"},
        )

        # When no failed_step_number, executed_steps and agent_outputs are not modified
        assert updates["retry_count"] == 1
        assert updates["errors"] == []
        assert updates["should_retry"] is True


class TestErrorHandlerConstants:
    """Test error handling constants."""

    def test_max_retries_default(self):
        """MAX_RETRIES should be 3."""
        assert MAX_RETRIES == 3

    def test_error_severity_values(self):
        """ErrorSeverity should have expected values."""
        assert ErrorSeverity.LOW.value == "low"
        assert ErrorSeverity.MEDIUM.value == "medium"
        assert ErrorSeverity.HIGH.value == "high"
        assert ErrorSeverity.CRITICAL.value == "critical"
