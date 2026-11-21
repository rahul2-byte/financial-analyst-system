"""Concurrent execution of the tool calls from one assistant turn.

The AgentLoop still *consumes* results one call at a time, in the model's
original order (history, evidence accounting and events are unchanged). This
module only starts the executable calls early so their latencies overlap.

Calls that share an evidence family and ticker (for example ``fetch_stock_data``
and ``get_technical_overview``, which share one OHLCV cache) run one after
another inside a single lane, exactly as they did when everything was serial, so
the second call still hits the first call's cache instead of re-fetching. Lanes
run concurrently with each other.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.agent_loop.tool_execution import ToolExecutor

_OHLCV_TOOLS = frozenset(
    {
        "data:fetch_stock_data",
        "analysis:get_technical_overview",
        "analysis:run_technical_scan",
    }
)
_FUNDAMENTAL_TOOLS = frozenset(
    {"data:fetch_fundamentals", "analysis:run_fundamental_scan"}
)


@dataclass(frozen=True)
class ToolOutcome:
    payload: dict[str, Any]
    duration_ms: float


def lane_key(call_id: str, name: str, arguments: dict[str, Any]) -> str:
    """Calls with the same key must not overlap (they share runner caches)."""
    ticker = " ".join(str(arguments.get("ticker", "")).split()).upper()
    if ticker and name in _OHLCV_TOOLS:
        return f"ohlcv:{ticker}"
    if ticker and name in _FUNDAMENTAL_TOOLS:
        return f"fundamentals:{ticker}"
    if name == "news:fetch_news":
        # News is its own lane: it never waits behind OHLCV/fundamentals calls.
        return f"news:{ticker or call_id}"
    return f"call:{call_id}"


class ToolBatch:
    """Start tool calls early; hand back each outcome when the loop asks."""

    def __init__(
        self,
        executor: ToolExecutor,
        max_seconds: Callable[[], float],
    ) -> None:
        self._executor = executor
        self._max_seconds = max_seconds
        self._futures: dict[str, asyncio.Future[ToolOutcome]] = {}
        self._tasks: list[asyncio.Task[None]] = []

    def __contains__(self, call_id: str) -> bool:
        return call_id in self._futures

    def launch(self, calls: list[tuple[str, str, dict[str, Any]]]) -> None:
        """Start ``(call_id, name, arguments)`` calls; lanes run concurrently."""
        loop = asyncio.get_running_loop()
        lanes: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
        for call_id, name, arguments in calls:
            if call_id in self._futures:
                continue
            self._futures[call_id] = loop.create_future()
            lanes.setdefault(lane_key(call_id, name, arguments), []).append(
                (call_id, name, arguments)
            )
        for lane in lanes.values():
            self._tasks.append(asyncio.create_task(self._run_lane(lane)))

    async def _run_lane(self, lane: list[tuple[str, str, dict[str, Any]]]) -> None:
        for call_id, name, arguments in lane:
            future = self._futures[call_id]
            started = time.perf_counter()
            try:
                payload = await self._executor.execute(
                    name, arguments, max_seconds=max(1.0, self._max_seconds())
                )
            except asyncio.CancelledError:
                for pending_id, _, _ in lane[lane.index((call_id, name, arguments)) :]:
                    self._futures[pending_id].cancel()
                raise
            except Exception as exc:  # noqa: BLE001 - isolate one call from its siblings
                if not future.done():
                    future.set_exception(exc)
                continue
            if not future.done():
                future.set_result(
                    ToolOutcome(
                        payload=payload,
                        duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    )
                )

    async def result(self, call_id: str) -> ToolOutcome:
        return await self._futures[call_id]

    async def aclose(self) -> None:
        """Cancel anything still running and retrieve unconsumed outcomes."""
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        for future in self._futures.values():
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()
        self._tasks.clear()
