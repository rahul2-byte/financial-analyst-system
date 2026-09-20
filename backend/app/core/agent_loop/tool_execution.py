"""Tool invocation boundary for the AgentLoop."""

from __future__ import annotations

from typing import Any

import httpx
from app.core.agent_loop.model_events import result_payload
from app.core.guardrails import validate_tool_arguments
from app.core.observability import observe
from app.observability.tracing import set_current_span_attributes
from app.security.policy import redact_secrets


class ToolExecutor:
    """Normalize successful and failed tool calls into one payload contract."""

    def __init__(self, runner: Any, allowed_tools: set[str] | None = None) -> None:
        self._runner = runner
        self._allowed_tools = allowed_tools

    @observe("tool.execute", as_type="tool")
    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
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
            payload = result_payload(await self._runner.execute(name, arguments))
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


def _result_count(payload: dict[str, Any]) -> int:
    for key in ("results", "sources", "documents", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return 0
