"""Phase 1 regression tests for tool execution, caching and grounding."""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from app.core.agent_loop import FinancialToolRunner
from app.core.agent_loop.evidence import extract_evidence_facts
from app.core.agent_loop.tool_execution import ToolExecutor
from app.core.resources import RuntimeResources
from app.models.routing import ExecutionMode, ModelTier, RoutePlan
from finai.session_runtime import _grounded_text, _run_direct_tool


def _prov(dataset: str = "historical_prices", quality: str = "verified") -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "source": "yfinance",
        "dataset": dataset,
        "instrument": "ABC.NS",
        "observed_at": now,
        "ingested_at": now,
        "version": "v1",
        "quality_status": quality,
        "as_of": now,
    }


def _rows(days_ago: int = 1) -> list[dict[str, Any]]:
    base = datetime.now(UTC) - timedelta(days=days_ago)
    ts0, ts1 = (base - timedelta(days=1)).isoformat(), base.isoformat()
    return [
        {"timestamp": ts0, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 5},
        {"timestamp": ts1, "open": 10, "high": 13, "low": 10, "close": 12, "volume": 5},
    ]


class _YF:
    def __init__(self) -> None:
        self.price_calls = 0
        self.release = threading.Event()
        self.block = False

    def fetch_stock_price(self, ticker, period, interval):
        self.price_calls += 1
        if self.block:
            self.release.wait(5)
        return {
            "ticker": ticker,
            "period": period,
            "interval": interval,
            "data": _rows(),
            "provenance": _prov(),
            "quality_issues": [],
        }

    def fetch_company_fundamentals(self, ticker):
        return {"ticker": ticker, "peRatio": 21.5, "returnOnEquity": 0.18}


def _runner(yf: Any, upstox: Any = None) -> FinancialToolRunner:
    return FinancialToolRunner(
        RuntimeResources(llm_service=object(), yf_fetcher=yf, upstox_fetcher=upstox)
    )


async def test_slow_sync_tool_times_out_and_loop_stays_responsive() -> None:
    yf = _YF()
    yf.block = True
    executor = ToolExecutor(_runner(yf), timeout_seconds=0.3)
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    task = asyncio.create_task(ticker())
    try:
        result = await executor.execute("data:fetch_stock_data", {"ticker": "ABC.NS"})
    finally:
        task.cancel()
        yf.release.set()
    assert result["success"] is False
    assert result["error_type"] == "tool_timeout"
    assert ticks >= 5  # loop kept running while the provider call blocked


async def test_cancellation_propagates_through_executor() -> None:
    yf = _YF()
    yf.block = True
    executor = ToolExecutor(_runner(yf), timeout_seconds=10)
    task = asyncio.create_task(
        executor.execute("data:fetch_stock_data", {"ticker": "ABC.NS"})
    )
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    yf.release.set()


async def test_unexpected_tool_exception_becomes_structured_error() -> None:
    class Boom:
        async def execute(self, name, arguments):
            raise TypeError("bug in tool")

    result = await ToolExecutor(Boom()).execute("data:fetch_market_status", {})
    assert result["success"] is False
    assert result["error_type"] == "tool_internal_error"
    assert "TypeError" in result["error"]


async def test_ohlcv_cache_expires_by_interval() -> None:
    yf = _YF()
    runner = _runner(yf)
    now = [1000.0]
    for cache in (runner._ohlcv_by_request, runner._ohlcv_provenance_by_request):
        cache._clock = lambda: now[0]
    args = {"ticker": "ABC.NS", "period": "1mo", "interval": "5m"}
    await runner.execute("analysis:run_technical_scan", args)
    await runner.execute("analysis:run_technical_scan", args)
    assert yf.price_calls == 1
    now[0] += 61  # intraday TTL elapsed
    await runner.execute("analysis:run_technical_scan", args)
    assert yf.price_calls == 2
    daily = {"ticker": "ABC.NS", "period": "1mo", "interval": "1d"}
    await runner.execute("analysis:run_technical_scan", daily)
    now[0] += 61  # daily bars still fresh
    await runner.execute("analysis:run_technical_scan", daily)
    assert yf.price_calls == 3
    now[0] += 1000
    await runner.execute("analysis:run_technical_scan", daily)
    assert yf.price_calls == 4


async def test_fundamentals_become_citable_facts_with_units() -> None:
    runner = _runner(_YF())
    runner.reset_turn_evidence()
    result = await runner.execute("data:fetch_fundamentals", {"ticker": "ABC.NS"})
    assert result["provenance"]["quality_status"] == "degraded"
    facts = extract_evidence_facts(result)
    pe = facts["fundamentals_snapshot:ABC.NS:data.peRatio"]
    assert pe.value == 21.5
    assert pe.unit == "ratio"
    assert pe.instrument == "ABC.NS"
    assert pe.observed_at.tzinfo is not None
    assert runner.turn_facts.keys() == facts.keys()


class _Upstox:
    def __init__(self, days_ago: int = 1) -> None:
        self.days_ago = days_ago
        self.span: timedelta | None = None

    def resolve_instrument(self, ticker):
        return [{"instrument_key": "NSE_EQ|ABC", "isin": "X"}]

    def fetch_candles(self, key, *, start, end):
        self.span = end - start
        return _rows(self.days_ago)


async def test_upstox_technical_overview_honours_period_and_has_provenance() -> None:
    upstox = _Upstox()
    runner = _runner(_YF(), upstox)
    result = await runner.execute(
        "analysis:get_technical_overview",
        {"ticker": "ABC.NS", "period": "1mo", "interval": "1d"},
    )
    assert result["success"] is True
    assert upstox.span is not None and upstox.span.days == 31
    prov = result["provenance"]
    assert prov["source"] == "upstox"
    assert prov["dataset"] == "historical_prices"
    assert prov["observed_at"] and prov["ingested_at"]


async def test_stale_upstox_candles_fall_back_to_yfinance() -> None:
    yf = _YF()
    runner = _runner(yf, _Upstox(days_ago=60))
    result = await runner.execute(
        "analysis:get_technical_overview", {"ticker": "ABC.NS", "interval": "1d"}
    )
    assert yf.price_calls == 1
    assert result["provenance"]["source"] == "yfinance"


def _route(allowed: set[str]) -> RoutePlan:
    return RoutePlan.model_construct(
        intent="lookup",
        execution_mode=ExecutionMode.TOOL_ONLY,
        required_tools=["data:fetch_fundamentals"],
        allowed_tools=allowed,
        model_tier=ModelTier.NONE,
        confidence=1.0,
    )


async def _direct(allowed: set[str]) -> list[Any]:
    return [
        event
        async for event in _run_direct_tool(
            _runner(_YF()),
            "data:fetch_fundamentals",
            {"ticker": "ABC.NS"},
            "q",
            uuid4(),
            _route(allowed),
            None,
        )
    ]


async def test_direct_tool_enforces_allowlist() -> None:
    events = await _direct({"data:fetch_stock_data"})
    assert any(e.type == "tool.failed" for e in events)
    assert events[-1].terminal_status == "insufficient_data"


async def test_direct_degraded_fundamentals_not_reported_complete() -> None:
    events = await _direct({"data:fetch_fundamentals"})
    assert events[-1].terminal_status == "completed"
    assert events[-1].evidence_status == "limited"


def test_freeform_numbers_must_be_bound_to_evidence() -> None:
    runner = _runner(_YF())
    runner.reset_turn_evidence()
    assert _grounded_text(runner, "PE is 99.9x") == "PE is 99.9x"  # no tools ran
    runner.turn_evidence_tools = 1
    runner.turn_facts = extract_evidence_facts(
        {
            "data": {"peRatio": 21.5},
            "provenance": _prov("fundamentals_snapshot", "degraded"),
        }
    )
    assert _grounded_text(runner, "P/E is 21.5 today.") == "P/E is 21.5 today."
    assert _grounded_text(runner, "No numbers here.") == "No numbers here."
    guarded = _grounded_text(runner, "P/E is 37.2 today.")
    assert "37.2" not in guarded
    assert "could not verify" in guarded


_NON_CLAIMS = [
    "In 2025 the company grew steadily.",
    "Guidance for FY2026 was reiterated.",
    "Results for Q3 FY26 are due.",
    "As of 20 Nov the trend is up.",
    "On Nov 20, 2026 volumes were light.",
    "The 50-day SMA acts as support.",
    "Price is above the 200 DMA.",
    "RSI(14) is neutral.",
    "MACD 12/26/9 shows a crossover.",
    "Over the last 6 months it rallied.",
    "It is near its 52-week high.",
    "The market closes at 15:30 IST.",
    "A 14-period RSI is common.",
    "There are 3 key risks.",
    "1. First point\n2. Second point",
]


@pytest.mark.parametrize("text", _NON_CLAIMS)
def test_non_claim_numbers_do_not_trigger_fallback(text: str) -> None:
    runner = _runner(_YF())
    runner.turn_evidence_tools = 1
    assert _grounded_text(runner, text) == text


@pytest.mark.parametrize(
    "text", ["Revenue was 12bn.", "Up 45%.", "Price Rs 2,450.", "Profit 3Cr.", "At 5x."]
)
def test_real_claims_still_need_evidence(text: str) -> None:
    runner = _runner(_YF())
    runner.turn_evidence_tools = 1
    assert _grounded_text(runner, text) != text


def _freeform_runner(answer: str) -> Any:
    from finai.session_runtime import ResearchRunner

    call = {
        "index": 0,
        "id": "c1",
        "type": "function",
        "function": {
            "name": "data:fetch_stock_data",
            "arguments": '{"ticker":"TCS.NS"}',
        },
    }

    class Model:
        calls = 0

        def generate_stream(self, messages, model, **kwargs):
            Model.calls += 1
            first = Model.calls == 1

            async def stream():
                delta = {"tool_calls": [call]} if first else {"content": answer}
                yield {"event": "chunk", "data": {"choices": [{"delta": delta}]}}

            return stream()

    class Policy:
        async def decide(self, *args, **kwargs):
            return RoutePlan(
                intent="general_question",
                execution_mode=ExecutionMode.MODEL_ANSWER,
                required_tools=[],
                allowed_tools={"data:fetch_stock_data"},
                model_tier=ModelTier.MAIN,
                confidence=1.0,
            )

    return ResearchRunner(
        RuntimeResources(
            llm_service=Model(), yf_fetcher=_YF(), routing_policy=Policy()
        ),
        "autonomous",
    )


async def _run_freeform(answer: str) -> str:
    from app.models.request_models import Message

    fixture = {
        "name": "data:fetch_stock_data",
        "response": {
            "success": True,
            "data": {
                "ticker": "TCS.NS",
                "period": "1y",
                "interval": "1d",
                "latest": {"close": 4012.5},
                "sma_50": 3950,
                "rsi_14": 61.2,
            },
            "provenance": _prov(),
        },
    }
    runner = _freeform_runner(answer)
    query = "How is TCS doing technically?"
    events = [
        e
        async for e in runner.stream(
            [Message(role="user", content=query)],
            query,
            uuid4(),
            mocked_tools=[fixture],
        )
    ]
    return "".join(e.text for e in events if e.type == "response.delta")


_GOOD = (
    "TCS closed at ₹4,012.50 on 20 Nov 2026; the 50-day SMA is 3,950 "
    "and RSI(14) is 61.2"
)


async def test_end_to_end_grounded_freeform_answer_passes_unchanged() -> None:
    assert await _run_freeform(_GOOD) == _GOOD


async def test_end_to_end_invented_number_is_replaced_by_fallback() -> None:
    text = await _run_freeform(_GOOD + " with a P/E of 31")
    assert "P/E of 31" not in text
    assert "could not verify" in text


async def test_provider_unavailable_is_retryable_without_traceback(caplog) -> None:
    import logging

    from data.retry import ProviderUnavailable

    class Down:
        async def execute(self, name, arguments):
            raise ProviderUnavailable("yfinance", "connection refused", attempts=3)

    with caplog.at_level(logging.DEBUG):
        result = await ToolExecutor(Down()).execute(
            "data:fetch_stock_data", {"ticker": "ABC.NS"}
        )
    assert result["success"] is False
    assert result["retryable"] is False
    assert result["error_type"] == "provider_unavailable"
    assert "unavailable" in result["error"]
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not [r for r in caplog.records if r.exc_info]


async def test_agent_loop_reports_provider_outage_as_evidence_failure() -> None:
    from app.core.agent_loop import AgentLoop, AgentLoopConfig
    from app.core.prompts import PromptRegistry
    from app.models.request_models import Message
    from data.retry import ProviderUnavailable

    prompts = PromptRegistry.bundled()
    seen: list[list[Message]] = []

    def call(index: int) -> dict[str, Any]:
        return {
            "index": 0,
            "id": f"c{index}",
            "type": "function",
            "function": {
                "name": "data:fetch_stock_data",
                "arguments": '{"ticker":"ABC.NS"}',
            },
        }

    class Model:
        calls = 0

        def generate_stream(self, messages, model, **kwargs):
            Model.calls += 1
            seen.append(list(messages))
            n = Model.calls

            async def stream():
                delta = (
                    {"tool_calls": [call(n)]}
                    if n <= 2
                    else {"content": "The data provider was unavailable."}
                )
                yield {"event": "chunk", "data": {"choices": [{"delta": delta}]}}

            return stream()

    class Tools:
        def definitions(self):
            return [{"type": "function", "function": {"name": "data:fetch_stock_data"}}]

        async def execute(self, name, arguments):
            raise ProviderUnavailable("yfinance", "connection refused", attempts=3)

    loop = AgentLoop(
        Model(),
        Tools(),
        config=AgentLoopConfig(model="m", answer_contract="freeform"),
    )
    written: list[Message] = []
    events = [
        e
        async for e in loop.run(
            [Message(role="user", content="price of ABC")],
            conversation_id=uuid4(),
            message_writer=written.append,
        )
    ]
    final = events[-1]
    assert final.type == "run.completed"
    assert final.terminal_status == "insufficient_data"
    assert not any(e.type == "run.failed" for e in events)  # no repeated-call error
    assert len(seen) == 1  # not retried by the loop
    contents = [m.content for m in written]
    assert prompts.get("agent_loop.tool.evidence_failure") in contents
    assert prompts.get("agent_loop.tool.invalid_arguments") not in contents
