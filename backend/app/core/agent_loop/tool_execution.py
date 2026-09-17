"""Tool invocation boundary for the AgentLoop."""

from __future__ import annotations

from typing import Any

from app.core.agent_loop.model_events import result_payload


class ToolExecutor:
    """Normalize successful and failed tool calls into one payload contract."""

    def __init__(self, runner: Any) -> None:
        self._runner = runner

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return result_payload(await self._runner.execute(name, arguments))
        except Exception as exc:  # noqa: BLE001 - tool boundary must not abort the run
            return {"success": False, "error": str(exc)}
