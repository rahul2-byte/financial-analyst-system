"""Tool invocation boundary for the AgentLoop."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx
from app.core.agent_loop.model_events import result_payload
from app.core.guardrails import validate_tool_arguments
from app.core.observability import observe
from app.observability.tracing import set_current_span_attributes
from app.security.policy import redact_secrets
from data.retry import ProviderUnavailable

logger = logging.getLogger(__name__)

DEFAULT_TOOL_TIMEOUT_SECONDS = 30.0
# Tools with their own longer internal budgets, or that wait on a human.
_TOOL_TIMEOUT_OVERRIDES: dict[str, float | None] = {
    "interaction:ask_user": None,
}


def news_tool_timeout() -> float:
    """News budget: the pipeline deadline plus a small grace, never more."""
    from app.config import settings

    return float(settings.NEWS_PIPELINE_TOTAL_TIMEOUT) + float(
        settings.NEWS_TOOL_GRACE_SECONDS
    )


def default_tool_timeout() -> float:
    """Per-tool timeout in seconds; override with FINAI_TOOL_TIMEOUT_SECONDS."""
    raw = os.environ.get("FINAI_TOOL_TIMEOUT_SECONDS")
    if raw:
        try:
            value = float(raw)
        except ValueError:
            return DEFAULT_TOOL_TIMEOUT_SECONDS
        if value > 0:
            return value
    return DEFAULT_TOOL_TIMEOUT_SECONDS


class ToolExecutor:
    """Normalize successful and failed tool calls into one payload contract."""

    def __init__(
        self,
        runner: Any,
        allowed_tools: set[str] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self._runner = runner
        self._allowed_tools = allowed_tools
        self._timeout_seconds = timeout_seconds

    def _timeout_for(self, name: str) -> float | None:
        if name == "news:fetch_news" and self._timeout_seconds is None:
            return news_tool_timeout()
        if name in _TOOL_TIMEOUT_OVERRIDES and self._timeout_seconds is None:
            return _TOOL_TIMEOUT_OVERRIDES[name]
        if self._timeout_seconds is not None:
            return self._timeout_seconds
        return default_tool_timeout()

    @observe("tool.execute", as_type="tool")
    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        max_seconds: float | None = None,
    ) -> dict[str, Any]:
        try:
            if self._allowed_tools is not None and name not in self._allowed_tools:
                return {
                    "success": False,
                    "error": "tool is not authorized for this run",
                }
            if name in {
                "data:fetch_stock_data",
                "data:fetch_fundamentals",
                "news:fetch_news",
                "analysis:run_fundamental_scan",
                "analysis:run_technical_scan",
                "analysis:get_technical_overview",
                "interaction:ask_user",
            }:
                try:
                    arguments = validate_tool_arguments(name, arguments)
                except ValueError as exc:
                    return {
                        "success": False,
                        "retryable": True,
                        "error": f"Invalid arguments for {name}: {exc}",
                    }
            timeout = self._timeout_for(name)
            if max_seconds is not None and timeout is not None:
                timeout = min(timeout, max_seconds)
            try:
                async with asyncio.timeout(timeout):
                    raw = await self._runner.execute(name, arguments)
            except TimeoutError:
                if timeout is None:
                    raise
                logger.warning("tool %s timed out after %ss", name, timeout)
                set_current_span_attributes(
                    {
                        "tool.name": name,
                        "tool.status": "failed",
                        "error.type": "timeout",
                    }
                )
                return {
                    "success": False,
                    "retryable": False,
                    "error_type": "tool_timeout",
                    "error": f"Tool {name} timed out after {timeout:g}s",
                }
            payload = result_payload(raw)
            set_current_span_attributes(
                {
                    "tool.name": name,
                    "tool.status": "success" if payload.get("success") else "failed",
                    "tool.result_count": _result_count(payload),
                }
            )
            return payload
        except (
            TimeoutError,
            OSError,
            ConnectionError,
            ValueError,
            KeyError,
            httpx.HTTPError,
        ) as exc:
            set_current_span_attributes(
                {
                    "tool.name": name,
                    "tool.status": "failed",
                    "error.type": type(exc).__name__,
                }
            )
            return {"success": False, "error": str(redact_secrets(str(exc)))}
        except ProviderUnavailable as exc:
            logger.warning(
                "tool %s: provider unavailable: %s", name, type(exc).__name__
            )
            set_current_span_attributes(
                {
                    "tool.name": name,
                    "tool.status": "failed",
                    "error.type": "ProviderUnavailable",
                }
            )
            return {
                "success": False,
                "retryable": False,
                "error_type": "provider_unavailable",
                "error": str(redact_secrets(str(exc))),
            }
        except Exception as exc:
            logger.exception("tool %s raised an unexpected error", name)
            set_current_span_attributes(
                {
                    "tool.name": name,
                    "tool.status": "failed",
                    "error.type": type(exc).__name__,
                }
            )
            return {
                "success": False,
                "retryable": False,
                "error_type": "tool_internal_error",
                "error": f"Tool {name} failed unexpectedly: {type(exc).__name__}",
            }


def _result_count(payload: dict[str, Any]) -> int:
    for key in ("results", "sources", "documents", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return 0
