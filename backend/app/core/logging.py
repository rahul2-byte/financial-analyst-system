"""
Unified logging configuration for the Financial Intelligence Platform.

This module provides:
- Structured logging setup
- Session-based audit logging
- Logger factory functions

Usage:
    from app.core.logging import get_logger, setup_logging

    logger = get_logger(__name__)
    logger.info("Message")
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from functools import wraps

# ============================================================================
# Logging Configuration
# ============================================================================


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configures structured logging for the application.

    Args:
        log_level: The logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Silence overly verbose loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name: The logger name (typically __name__)

    Returns:
        A configured logger instance
    """
    return logging.getLogger(name)


# ============================================================================
# Session Logging (Audit Trail)
# ============================================================================


class SessionLogger:
    """
    Manages session-specific logs for research queries.
    Logs are stored in 'logs/research_sessions/' with audit trail format.

    Usage:
        logger = SessionLogger("Analyze AAPL")
        logger.log_step("PLANNER", "Generated execution plan", parameters={"steps": 3})
        logger.log_error("EXECUTION", "API timeout", data={"error": "timeout"})
    """

    RETENTION_DAYS = 7

    def __init__(self, query: str, trace_id: Optional[str] = None):
        """
        Initialize a session logger.

        Args:
            query: The user's research query
            trace_id: Optional trace ID (will generate if not provided)
        """
        self.query = query
        self.trace_id = trace_id or self._generate_trace_id()
        self.timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Resolve path relative to backend directory
        backend_root = Path(__file__).parent.parent.parent.resolve()
        self.session_dir = backend_root / "logs" / "research_sessions"
        self.log_file = self.session_dir / f"{self.timestamp}_{self.trace_id}.log"

        # Ensure directory exists
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Initialize log with header and cleanup old logs
        self._initialize_log()
        self._cleanup_old_logs()

    def _generate_trace_id(self) -> str:
        """Generate a simple trace ID."""
        import random
        import string

        return "".join(random.choices(string.hexdigits.lower(), k=16))

    def _initialize_log(self):
        """Write the header to the log file."""
        header = f"""
================================================================================
FINAI RESEARCH SESSION AUDIT TRAIL
================================================================================
QUERY: {self.query}
TRACE_ID: {self.trace_id}
START_TIME: {datetime.now(timezone.utc).isoformat()}
================================================================================
"""
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(header)

    def log_step(
        self,
        step_name: str,
        explanation: str,
        parameters: Optional[dict] = None,
        data: Any = None,
    ):
        """
        Log a single research step with metadata and structured data.

        Args:
            step_name: Name of the step (e.g., "PLANNER", "EXECUTION")
            explanation: What happened
            parameters: Optional parameters dict
            data: Optional output data
        """
        entry = f"""
[STEP: {step_name.upper()}]
TIMESTAMP: {datetime.now(timezone.utc).isoformat()}
EXPLANATION: {explanation}
"""
        if parameters:
            entry += "--------------------------------------------------------------------------------\n"
            entry += "PARAMETERS:\n"
            try:
                entry += json.dumps(parameters, indent=2) + "\n"
            except (TypeError, ValueError):
                entry += str(parameters) + "\n"

        if data is not None:
            entry += "--------------------------------------------------------------------------------\n"
            entry += "DATA / OUTPUT:\n"
            try:
                if isinstance(data, (dict, list)):
                    entry += json.dumps(data, indent=2) + "\n"
                elif hasattr(data, "model_dump"):
                    entry += json.dumps(data.model_dump(), indent=2) + "\n"
                else:
                    entry += str(data) + "\n"
            except Exception:
                entry += str(data) + "\n"

        entry += "================================================================================\n"

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(entry)

    def log_error(self, error_name: str, message: str, data: Any = None):
        """
        Log an error in the audit trail.

        Args:
            error_name: Name of the error
            message: Error message
            data: Optional error data
        """
        self.log_step(f"ERROR_{error_name}", message, data=data)

    def _cleanup_old_logs(self):
        """Delete session logs older than the retention policy."""
        try:
            now = datetime.now()
            cutoff = now - timedelta(days=self.RETENTION_DAYS)

            for log_file in self.session_dir.glob("*.log"):
                if log_file.stat().st_mtime < cutoff.timestamp():
                    os.remove(log_file)
                    get_logger(__name__).info(
                        f"Deleted old session log: {log_file.name}"
                    )
        except Exception as e:
            get_logger(__name__).error(f"Failed to cleanup old logs: {e}")

    @staticmethod
    def get_logger(query: str) -> "SessionLogger":
        """
        Factory method to create a session logger.

        Args:
            query: The research query

        Returns:
            A new SessionLogger instance
        """
        return SessionLogger(query)


# ============================================================================
# Convenience Functions
# ============================================================================


# Module-level logger for use in this module
_logger = get_logger(__name__)


def log_function_call(func):
    """
    Decorator to automatically log function calls.

    Usage:
        @log_function_call
        def my_function(arg1, arg2):
            pass
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        _logger.debug(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
        try:
            result = func(*args, **kwargs)
            _logger.debug(f"{func.__name__} returned: {result}")
            return result
        except Exception as e:
            _logger.error(f"{func.__name__} raised {type(e).__name__}: {e}")
            raise

    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        _logger.debug(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
        try:
            result = await func(*args, **kwargs)
            _logger.debug(f"{func.__name__} returned: {result}")
            return result
        except Exception as e:
            _logger.error(f"{func.__name__} raised {type(e).__name__}: {e}")
            raise

    import asyncio

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return wrapper
