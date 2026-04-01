"""
Error handling system for the Financial Intelligence Platform.

This module provides:
- Error severity classification
- Retriable error detection
- Exponential backoff for retries
- Error handler classes

Usage:
    from app.core.error_handling import ErrorHandler, should_retry, apply_backoff

    if should_retry(error_msg):
        await apply_backoff(retry_count)
"""

import asyncio
import logging
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum
from app.core.policies.retry_policy import (
    MAX_BACKOFF_SECONDS,
    MAX_RETRIES,
    exponential_backoff_seconds,
)

logger = logging.getLogger(__name__)

class ErrorSeverity(str, Enum):
    """Classification of error severity."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


RETRIABLE_ERROR_PATTERNS: list[str] = [
    "timeout",
    "connection",
    "network",
    "temporary",
    "rate limit",
]

CRITICAL_ERROR_PATTERNS: list[str] = [
    "authentication",
    "authorization",
    "quota exceeded",
]


def should_retry(error_msg: str) -> bool:
    """
    Determine if an error is retriable.

    Args:
        error_msg: The error message to analyze

    Returns:
        True if the error should be retried
    """
    error_lower = error_msg.lower()
    return not any(crit in error_lower for crit in CRITICAL_ERROR_PATTERNS)


def get_error_severity(error_msg: str) -> ErrorSeverity:
    """
    Determine error severity from message.

    Args:
        error_msg: The error message to analyze

    Returns:
        ErrorSeverity classification
    """
    error_lower = error_msg.lower()
    if any(crit in error_lower for crit in CRITICAL_ERROR_PATTERNS):
        return ErrorSeverity.CRITICAL
    if any(ret in error_lower for ret in RETRIABLE_ERROR_PATTERNS):
        return ErrorSeverity.HIGH
    return ErrorSeverity.MEDIUM


async def apply_backoff(retry_count: int) -> None:
    """
    Apply exponential backoff before retrying.

    Args:
        retry_count: Current retry attempt number (0-indexed)

    Formula: min(2^retry_count, MAX_BACKOFF_SECONDS)
    """
    backoff_time = exponential_backoff_seconds(retry_count)
    logger.info(
        f"Applying backoff of {backoff_time}s before retry (attempt {retry_count + 1})"
    )
    await asyncio.sleep(backoff_time)


@dataclass
class ErrorContext:
    """Context information for an error."""

    errors: List[str]
    retry_count: int
    failed_node: Optional[str] = None
    failed_step_number: Optional[int] = None


@dataclass
class ErrorAction:
    """Result of error handling decision."""

    should_retry: bool = False
    should_escalate: bool = False
    new_retry_count: int = 0
    cleanup_steps: Optional[List[int]] = None


class ErrorHandler:
    """
    Centralized error handling with retry logic.

    Usage:
        handler = ErrorHandler(max_retries=3)
        action = handler.decide(errors, retry_count)

        if action.should_retry:
            await apply_backoff(action.new_retry_count)
    """

    def __init__(self, max_retries: int = MAX_RETRIES):
        self.max_retries = max_retries

    def should_continue(self, errors: List[str], retry_count: int) -> bool:
        """
        Determine if execution should continue.

        Args:
            errors: List of error messages
            retry_count: Current retry count

        Returns:
            True if should continue (retry)
        """
        if retry_count >= self.max_retries:
            return False
        return all(should_retry(str(e)) for e in errors)

    def decide(self, error_context: ErrorContext) -> ErrorAction:
        """
        Decide on action based on error context.

        Args:
            error_context: Error context with errors and state

        Returns:
            ErrorAction with retry/escalate decision
        """
        errors = error_context.errors
        retry_count = error_context.retry_count

        if not errors:
            return ErrorAction(should_retry=False, should_escalate=False)

        if not self.should_continue(errors, retry_count):
            return ErrorAction(should_retry=False, should_escalate=True)

        return ErrorAction(
            should_retry=True,
            should_escalate=False,
            new_retry_count=retry_count + 1,
            cleanup_steps=(
                [error_context.failed_step_number]
                if error_context.failed_step_number
                else None
            ),
        )

    @staticmethod
    def create_cleanup_updates(
        retry_count: int,
        failed_step_number: Optional[int],
        executed_steps: List[dict],
        agent_outputs: dict,
    ) -> dict:
        """
        Create cleanup updates for retry.

        Args:
            retry_count: New retry count
            failed_step_number: Step that failed
            executed_steps: Current executed steps
            agent_outputs: Current agent outputs

        Returns:
            Dictionary of state updates
        """
        cleanup = {
            "retry_count": retry_count,
            "errors": [],
            "failed_node": None,
            "failed_step_number": None,
            "should_retry": True,
        }

        if failed_step_number is not None:
            cleaned_steps = [
                s for s in executed_steps if s.get("step_number") != failed_step_number
            ]
            cleanup["executed_steps"] = cleaned_steps

            outputs = dict(agent_outputs)
            outputs.pop(str(failed_step_number), None)
            cleanup["agent_outputs"] = outputs

        return cleanup


async def error_handler_node(state: dict, resources: "NodeResources") -> dict:
    """
    LangGraph node for error handling.

    Args:
        state: Current graph state
        resources: Node resources

    Returns:
        State updates based on error handling decision
    """
    errors = state.get("errors", [])
    retry_count = state.get("retry_count", 0)
    failed_node = state.get("failed_node")

    if failed_node == "planner_node":
        logger.error(f"Planner failed: {errors}. Cannot recover.")
        return {
            "should_retry": False,
            "should_escalate": True,
        }

    error_context = ErrorContext(
        errors=errors,
        retry_count=retry_count,
        failed_node=failed_node,
        failed_step_number=state.get("failed_step_number"),
    )

    handler = ErrorHandler(max_retries=MAX_RETRIES)
    action = handler.decide(error_context)

    if action.should_retry:
        logger.info(f"Retrying execution (attempt {retry_count + 1})")
        await apply_backoff(retry_count)

        return handler.create_cleanup_updates(
            retry_count=action.new_retry_count,
            failed_step_number=error_context.failed_step_number,
            executed_steps=state.get("executed_steps", []),
            agent_outputs=state.get("agent_outputs", {}),
        )

    logger.error(f"Execution failed with errors: {errors}")
    return {
        "should_retry": False,
        "should_escalate": action.should_escalate,
        "final_report": None,
    }
