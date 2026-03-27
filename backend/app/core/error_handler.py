import logging
from typing import Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


RETRIABLE_ERRORS = [
    "timeout",
    "connection",
    "network",
    "temporary",
    "rate limit",
]

CRITICAL_ERRORS = [
    "authentication",
    "authorization",
    "quota exceeded",
]


def should_retry(error_msg: str) -> bool:
    """Determine if an error is retriable."""
    error_lower = error_msg.lower()
    return not any(crit in error_lower for crit in CRITICAL_ERRORS)


def get_error_severity(error_msg: str) -> ErrorSeverity:
    """Determine error severity."""
    error_lower = error_msg.lower()
    if any(crit in error_lower for crit in CRITICAL_ERRORS):
        return ErrorSeverity.CRITICAL
    if any(ret in error_lower for ret in RETRIABLE_ERRORS):
        return ErrorSeverity.HIGH
    return ErrorSeverity.MEDIUM


class ErrorHandler:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    def should_continue(self, errors: List[str], retry_count: int) -> bool:
        """Determine if execution should continue."""
        if retry_count >= self.max_retries:
            return False
        return all(should_retry(str(e)) for e in errors)

    def get_action(self, errors: List[str], retry_count: int) -> str:
        """Get recommended action: 'retry', 'escalate', or 'end'."""
        if not errors:
            return "continue"

        if self.should_continue(errors, retry_count):
            return "retry"

        return "end"


async def error_handler_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node for error handling."""
    errors = state.get("errors", [])
    retry_count = state.get("retry_count", 0)

    handler = ErrorHandler(max_retries=3)
    action = handler.get_action(errors, retry_count)

    if action == "retry":
        logger.info(f"Retrying execution (attempt {retry_count + 1})")
        return {
            "retry_count": retry_count + 1,
            "errors": [],
            "should_retry": True,
        }

    logger.error(f"Execution failed with errors: {errors}")
    return {
        "should_retry": False,
        "should_escalate": action == "end",
        "final_report": None,
    }
