"""Runtime fixes from the hands-on usage test (reviewer outage, fallback, deadline)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

import httpx
import pytest
from app.core.agent_loop import AgentLoop, AgentLoopConfig
from app.events.models import EventFactory
from app.models.request_models import Message
from app.models.routing import NextAction
from app.services.chatgpt_codex_service import (
    ChatGPTCodexService,
    classify_fallback_reason,
)
from app.services.routing_policy import RoutingPolicy


class _Model:
    def __init__(self, text: str) -> None:
        self.text = text

    def generate_stream(self, messages: list[Message], model: str, **kwargs: Any):
        async def stream() -> Any:
            yield {"event": "token", "data": self.text}

        return stream()


class _Tools:
    def definitions(self) -> list[dict]:
        return []

    async def execute(self, name: str, arguments: dict) -> dict:
        return {"success": True}


class _Jev:
    def __init__(self, *, api_key: str | None, verdict: Any = None) -> None:
        self.api_key = api_key
        self.verdict = verdict
        self.calls = 0

    async def review_output(self, context: dict[str, Any]) -> NextAction:
        self.calls += 1
        if isinstance(self.verdict, Exception):
            raise self.verdict
        return self.verdict


async def _run(policy: RoutingPolicy, text: str = "safe answer") -> list[Any]:
    loop = AgentLoop(
        _Model(text),
        _Tools(),
        config=AgentLoopConfig(decision_provider=policy, answer_contract="freeform"),
    )
    return [
        e
        async for e in loop.run(
            [Message(role="user", content="hello")], conversation_id=uuid4()
        )
    ]


def _published(events: list[Any]) -> str:
    return "".join(getattr(e, "text", "") for e in events if e.type == "response.delta")


@pytest.mark.asyncio
async def test_no_reviewer_key_skips_review_and_delivers_answer() -> None:
    jev = _Jev(api_key=None, verdict=NextAction.DENY)
    events = await _run(RoutingPolicy(jev))  # type: ignore[arg-type]
    assert jev.calls == 0
    assert "safe answer" in _published(events)
    assert events[-1].type == "run.completed"
    assert events[-1].output_review == "not_configured"


@pytest.mark.asyncio
async def test_reviewer_outage_delivers_answer_and_marks_unavailable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    jev = _Jev(api_key="k", verdict=httpx.ConnectTimeout("slow"))
    with caplog.at_level(logging.WARNING):
        events = await _run(RoutingPolicy(jev))  # type: ignore[arg-type]
    assert jev.calls == 1
    assert "safe answer" in _published(events)
    assert events[-1].type == "run.completed"
    assert events[-1].output_review == "unavailable"
    assert any("ConnectTimeout" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_reviewer_deny_verdict_still_blocks_with_clear_message() -> None:
    jev = _Jev(api_key="k", verdict=NextAction.DENY)
    events = await _run(RoutingPolicy(jev), "UNSAFE-PAYLOAD")  # type: ignore[arg-type]
    assert "UNSAFE-PAYLOAD" not in _published(events)
    assert events[-1].type == "run.failed"
    assert events[-1].category == "output_policy"
    assert "reviewer verdict" in events[-1].message


@pytest.mark.asyncio
async def test_policy_propagates_reviewer_errors_instead_of_denying() -> None:
    policy = RoutingPolicy(_Jev(api_key="k", verdict=RuntimeError("down")))  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        await policy.review_output({})


@pytest.mark.parametrize(
    ("message", "timed_out", "expected"),
    [
        (
            'ChatGPT HTTP 429: {"error":{"type":"usage_limit_reached"}}',
            False,
            "quota",
        ),
        ("ChatGPT HTTP 429: slow down", False, "rate_limit"),
        ("ChatGPT HTTP 401: nope", False, "auth"),
        ("ChatGPT credentials unavailable", False, "auth"),
        ("TimeoutError", True, "timeout"),
        ("boom", False, "error"),
    ],
)
def test_classify_fallback_reason(message: str, timed_out: bool, expected: str) -> None:
    assert classify_fallback_reason(message, timed_out=timed_out) == expected


@pytest.mark.asyncio
async def test_provider_failed_event_carries_fallback_fields() -> None:
    class Hive:
        async def generate_stream(self, messages, model, **kwargs):
            yield {"event": "token", "data": "ok"}

    service = ChatGPTCodexService(
        client=httpx.AsyncClient(), fallback=Hive(), fallback_model="glm-test"
    )
    raw = [
        event
        async for event in service._fallback_stream(
            [Message(role="user", content="hi")],
            "gpt-test",
            'ChatGPT HTTP 429: {"error":{"type":"usage_limit_reached"}}',
        )
    ]
    failed = raw[0]["data"]
    assert failed["reason"] == "quota"
    assert failed["next_provider"] == "hive"
    assert failed["next_model"] == "glm-test"

    from app.events.models import ProviderFailed

    event = EventFactory(uuid4()).make(
        ProviderFailed,
        provider=failed["provider"],
        attempts=1,
        phase="unknown",
        message=failed["message"],
        fallback=failed["fallback"],
        reason=failed["reason"],
        next_provider=failed["next_provider"],
        next_model=failed["next_model"],
    )
    dumped = event.model_dump(mode="json")
    assert dumped["type"] == "provider.failed"
    assert dumped["reason"] == "quota"
    assert dumped["next_model"] == "glm-test"
    await service.aclose()


class _SlowTools:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def definitions(self) -> list[dict]:
        return [{"type": "function", "function": {"name": "data:lookup"}}]

    async def execute(self, name: str, arguments: dict) -> dict:
        self.calls.append(arguments["ticker"])
        await asyncio.sleep(0.15)
        return {"success": True, "data": {"ticker": arguments["ticker"]}}


class _TwoToolsThenText:
    def __init__(self) -> None:
        self.round = 0
        self.tools_offered: list[bool] = []

    def generate_stream(self, messages: list[Message], model: str, **kwargs: Any):
        self.round += 1
        self.tools_offered.append(bool(kwargs.get("tools")))
        round_number = self.round

        async def stream() -> Any:
            if round_number == 1:
                calls = [
                    {
                        "index": i,
                        "id": f"c{i}",
                        "type": "function",
                        "function": {
                            "name": "data:lookup",
                            "arguments": f'{{"ticker":"T{i}"}}',
                        },
                    }
                    for i in range(3)
                ]
                yield {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": calls}}]},
                }
            else:
                yield {"event": "token", "data": "Partial answer from evidence."}

        return stream()


@pytest.mark.asyncio
async def test_run_deadline_stops_tools_and_answers_from_evidence() -> None:
    model = _TwoToolsThenText()
    tools = _SlowTools()
    loop = AgentLoop(
        model,
        tools,
        config=AgentLoopConfig(max_run_seconds=0.2, answer_contract="freeform"),
    )
    events = [
        e
        async for e in loop.run(
            [Message(role="user", content="research T0 T1 T2")],
            conversation_id=uuid4(),
        )
    ]
    # Budget (0.2s) is exhausted after two 0.15s tools: the third is skipped.
    assert tools.calls == ["T0", "T1"]
    assert "Partial answer from evidence." in _published(events)
    assert events[-1].type == "run.completed"
    assert "run time budget" in (events[-1].completion_reason or "")
    assert model.round == 2


@pytest.mark.asyncio
async def test_completed_event_carries_router_reason_codes() -> None:
    from app.models.routing import RoutePlan

    route = RoutePlan(
        intent="research_report",
        reason="fallback",
        reason_codes=["router_failure"],
        confidence=0.0,
    )
    loop = AgentLoop(
        _Model("hello there"),
        _Tools(),
        config=AgentLoopConfig(answer_contract="freeform", route_plan=route),
    )
    events = [
        e
        async for e in loop.run(
            [Message(role="user", content="hi")], conversation_id=uuid4()
        )
    ]
    assert events[-1].type == "run.completed"
    assert events[-1].route_reason_codes == ["router_failure"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"error": "No data found", "ticker": "TATAMOTORS.NS"},
        {"ticker": "TATAMOTORS.NS", "data": []},
        {"ticker": "TATAMOTORS.NS", "data": None},
    ],
)
async def test_empty_price_history_reports_symbol_change(payload: dict) -> None:
    from app.core.agent_loop import FinancialToolRunner
    from app.core.resources import RuntimeResources

    class _EmptyFetcher:
        def fetch_stock_price(self, ticker: str, period: str, interval: str) -> dict:
            return dict(payload)

    runner = FinancialToolRunner(
        RuntimeResources(llm_service=object(), yf_fetcher=_EmptyFetcher())
    )
    result = await runner.execute("data:fetch_stock_data", {"ticker": "TATAMOTORS.NS"})
    assert result["success"] is False
    assert result["error"] == (
        "No price data for TATAMOTORS.NS; the symbol may have changed "
        "(e.g. after a demerger) or been delisted."
    )
    assert result["provenance"]
