import os
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from app.core.observability import langfuse_context

logger = logging.getLogger(__name__)


class SessionLogger:
    """
    Manages session-specific logs for research queries.
    Logs are stored in 'logs/research_sessions/' and follow a 'Decorated Text' format.
    """

    RETENTION_DAYS = 7

    def __init__(self, query: str):
        self.query = query
        self.trace_id = langfuse_context.get_current_trace_id()
        self.timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Resolve path relative to backend directory (one level up from app/core/)
        backend_root = Path(__file__).parent.parent.parent.resolve()
        self.session_dir = backend_root / "logs" / "research_sessions"
        self.log_file = self.session_dir / f"{self.timestamp}_{self.trace_id}.log"

        # Ensure directory exists
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Initialize log with header
        self._initialize_log()
        self._cleanup_old_logs()

    def _initialize_log(self):
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
        """Logs a single research step with metadata and structured data."""
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
        """Logs an error specifically in the audit trail."""
        self.log_step(f"ERROR_{error_name}", message, data=data)

    def _cleanup_old_logs(self):
        """Deletes session logs older than the retention policy."""
        try:
            now = datetime.now()
            cutoff = now - timedelta(days=self.RETENTION_DAYS)

            for log_file in self.session_dir.glob("*.log"):
                if log_file.stat().st_mtime < cutoff.timestamp():
                    os.remove(log_file)
                    logger.info(f"Deleted old session log: {log_file.name}")
        except Exception as e:
            logger.error(f"Failed to cleanup old logs: {e}")

    @staticmethod
    def get_logger(query: str) -> "SessionLogger":
        return SessionLogger(query)
