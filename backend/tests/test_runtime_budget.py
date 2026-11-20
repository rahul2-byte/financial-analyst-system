"""Run budget, sticky fallback and deterministic evidence summary."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from uuid import uuid4

import pytest
from app.core.agent_loop import AgentLoop, AgentLoopConfig
from app.models.request_models import Message
from app.models.routing import NextAction
from app.services.openrouter_service import OpenRouterProviderError

_TOOL = "data:fetch_stock_data"
_PAYLOAD = {
    "success": True,
    "data": {
        "ticker": "TCS.NS",
        "period": "1mo",
        "period_return_pct": 1.25,
        "latest": {"close": 3456.7, "timestamp": "2026-11-19T00:00:00+05:30"},
    },
    "provenance": {
        "source": "yfinance",
        "source_url": "https://finance.yahoo.com/quote/TCS.NS/history/",
        "observed_at": "2026-11-19T00:00:00+00:00",
        "quality_status": "verified",
    },
}


class _Tools:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    def definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {"name": _TOOL, "parameters": {"type": "object"}},
            }
        ]

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return _PAYLOAD if self.ok else {"success": False, "error": "nope"}


def _tool_call_event(index: int) -> dict[str, Any]:
    call = {
        "index": 0,
        "id": f"call-{index}",
        "type": "function",
        "function": {"name": _TOOL, "arguments": json.dumps({"ticker": "TCS.NS"})},
    }
    return {
        "event": "chunk",
        "data": {"choices": [{"delta": {"tool_calls": [call]}}]},
    }


class _Scripted:
    """First call requests a tool; later calls behave per ``later``."""

    def __init__(self, later: str, *, tool_first: bool = True) -> None:
        self.later = later
        self.tool_first = tool_first
        self.calls = 0

    def generate_stream(self, messages: list[Message], model: str, **kwargs: Any):
        self.calls += 1
        n = self.calls

        async def stream() -> Any:
            if n == 1 and self.tool_first:
                yield _tool_call_event(n)
                return
            if self.later == "500":
                raise OpenRouterProviderError(
                    'OpenRouter HTTP 500: {"status_code":500}'
                )
            if self.later == "hang":
                await asyncio.sleep(30)
            yield {"event": "token", "data": "final wrapped-up answer"}

        return stream()


async def _run(model: Any, tools: Any, **config: Any) -> list[Any]:
    loop = AgentLoop(
        model,
        tools,
        config=AgentLoopConfig(
            answer_contract="freeform",
            allowed_tools=frozenset({_TOOL}),
            **config,
        ),
    )
    return [
        e
        async for e in loop.run(
            [Message(role="user", content="TCS price")], conversation_id=uuid4()
        )
    ]


def _text(events: list[Any]) -> str:
    return "".join(getattr(e, "text", "") for e in events if e.type == "response.delta")


@pytest.mark.asyncio
async def test_hung_stream_is_cut_at_budget_and_wraps_up() -> None:
    class Model(_Scripted):
        def generate_stream(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
            if self.calls == 0:
                self.calls += 1

                async def hang() -> Any:
                    await asyncio.sleep(30)
                    yield {}

                return hang()
            return super().generate_stream(messages, model, **kwargs)

    model = Model("ok", tool_first=False)
    started = time.perf_counter()
    events = await _run(model, _Tools(), max_run_seconds=0.3, wrapup_grace_seconds=1.0)
    assert time.perf_counter() - started < 3
    assert events[-1].type == "run.completed"
    assert "final wrapped-up answer" in _text(events)
    assert events[-1].completion_reason


@pytest.mark.asyncio
async def test_hung_wrapup_after_tool_falls_back_to_evidence_summary() -> None:
    model = _Scripted("hang")
    started = time.perf_counter()
    events = await _run(model, _Tools(), max_run_seconds=0.3, wrapup_grace_seconds=0.3)
    assert time.perf_counter() - started < 3
    done = events[-1]
    assert done.type == "run.completed"
    assert done.completion_reason == "model_unavailable_evidence_summary"
    assert "3456.7" in _text(events)


@pytest.mark.asyncio
async def test_all_providers_500_after_tool_gives_evidence_summary() -> None:
    events = await _run(_Scripted("500"), _Tools())
    done = events[-1]
    assert done.type == "run.completed"
    assert done.completion_reason == "model_unavailable_evidence_summary"
    text = _text(events)
    assert text.startswith(
        "Model synthesis unavailable (HTTP 500). Evidence collected:"
    )
    assert "close 3456.7" in text
    assert "period_return_pct 1.25" in text
    assert "https://finance.yahoo.com/quote/TCS.NS/history/" in text


@pytest.mark.asyncio
async def test_all_providers_fail_without_tool_success_still_fails() -> None:
    events = await _run(_Scripted("500", tool_first=False), _Tools())
    assert events[-1].type == "run.failed"
    events = await _run(_Scripted("500"), _Tools(ok=False))
    assert events[-1].completion_reason is None
    assert "Model synthesis unavailable" not in _text(events)


@pytest.mark.asyncio
async def test_reviewer_deny_after_tool_success_stays_failed() -> None:
    class Deny:
        review_available = True

        async def review_output(self, context: dict[str, Any]) -> NextAction:
            return NextAction.DENY

    class Model(_Scripted):
        def generate_stream(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
            if self.calls == 0:
                return super().generate_stream(messages, model, **kwargs)
            self.calls += 1

            async def stream() -> Any:
                yield {"event": "token", "data": "UNSAFE-PAYLOAD"}

            return stream()

    events = await _run(Model("ok"), _Tools(), decision_provider=Deny())
    assert events[-1].type == "run.failed"
    assert events[-1].category == "output_policy"
    assert "Model synthesis unavailable" not in _text(events)
    assert "UNSAFE-PAYLOAD" not in _text(events)


@pytest.mark.asyncio
async def test_unexpected_bug_after_tool_success_stays_failed() -> None:
    class Model(_Scripted):
        def generate_stream(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
            if self.calls == 0:
                return super().generate_stream(messages, model, **kwargs)
            raise RuntimeError("bug")

    events = await _run(Model("ok"), _Tools())
    assert events[-1].type == "run.failed"
    assert "Model synthesis unavailable" not in _text(events)
