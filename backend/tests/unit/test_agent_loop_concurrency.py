"""Concurrent tool execution, the report fast path, and stage progress events."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from uuid import uuid4

import pytest
from app.core.agent_loop import AgentLoop, AgentLoopConfig
from app.models.request_models import Message
from app.models.routing import ExecutionMode, ModelTier, NextAction, RoutePlan
from app.services.routing_policy import RoutingPolicy

FACT = "prices:ABC.NS:data.latest.close"
STOCK = "data:fetch_stock_data"
TECH = "analysis:get_technical_overview"
FUND = "data:fetch_fundamentals"
SCAN = "analysis:run_fundamental_scan"
TSCAN = "analysis:run_technical_scan"
NEWS = "news:fetch_news"
ALL_TOOLS = [STOCK, TECH, TSCAN, FUND, SCAN, NEWS]

PAYLOAD = {
    "success": True,
    "data": {"latest": {"close": 123.4}},
    "provenance": {
        "source": "fixture",
        "dataset": "prices",
        "instrument": "ABC.NS",
        "observed_at": "2026-09-18T00:00:00+00:00",
        "ingested_at": "2026-09-18T00:01:00+00:00",
        "version": "fixture-1",
        "quality_status": "verified",
        "source_url": "https://fixture.example",
    },
}


class FakeTools:
    def __init__(
        self,
        delays: dict[str, float] | None = None,
        fail: set[str] | None = None,
        payloads: dict[str, dict] | None = None,
    ) -> None:
        self.payloads = payloads or {}
        self.delays = delays or {}
        self.fail = fail or set()
        self.spans: dict[str, tuple[float, float]] = {}
        self.cancelled: list[str] = []

    def definitions(self) -> list[dict]:
        return [{"type": "function", "function": {"name": n}} for n in ALL_TOOLS]

    async def execute(self, name: str, arguments: dict) -> dict:
        start = time.perf_counter()
        try:
            await asyncio.sleep(self.delays.get(name, 0.0))
        except asyncio.CancelledError:
            self.cancelled.append(name)
            raise
        self.spans[name] = (start, time.perf_counter())
        if name in self.fail:
            raise ValueError("boom")
        if name in self.payloads:
            return self.payloads[name]
        return {**PAYLOAD, "tool": name}


def _call(index: int, name: str, args: dict[str, Any] | None = None) -> dict:
    return {
        "index": index,
        "id": f"call-{index}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args or {"ticker": "ABC.NS"}),
        },
    }


def _draft() -> str:
    return json.dumps(
        {
            "executive_summary": f"Close [[fact:{FACT}]].",
            "key_drivers": ["Price evidence returned."],
            "detailed_analysis": f"Close [[fact:{FACT}]].",
            "risks": ["Coverage is limited."],
            "final_view": "Review.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": f"Close [[fact:{FACT}]].",
                    "importance": "major",
                    "evidence_refs": ["src"],
                    "numeric_refs": [FACT],
                }
            ],
            "citations": [{"citation_id": "src", "source_id": "prices"}],
        }
    )


class ScriptedModel:
    """Asks for ``tool_names`` while no tool result exists, then answers."""

    def __init__(self, tool_names: list[str], answer: str) -> None:
        self.tool_names = tool_names
        self.answer = answer
        self.requests: list[list[Message]] = []
        self.tools_offered: list[list[Any]] = []

    def generate_stream(self, messages: list[Message], model: str, **kwargs: Any):
        del model
        self.tools_offered.append(list(kwargs.get("tools") or []))
        self.requests.append(list(messages))
        has_results = any(m.role == "tool" for m in messages)

        async def stream() -> Any:
            if has_results:
                yield {"event": "token", "data": self.answer}
            else:
                calls = [_call(i, n) for i, n in enumerate(self.tool_names)]
                yield {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": calls}}]},
                }

        return stream()


def _tool_messages(model: ScriptedModel) -> list[str]:
    return [m.content for m in model.requests[-1] if m.role == "tool"]


async def _run(loop: AgentLoop, query: str = "look at ABC") -> list[Any]:
    return [
        e
        async for e in loop.run(
            [Message(role="user", content=query)], conversation_id=uuid4()
        )
    ]


def _freeform(model: ScriptedModel, tools: FakeTools, **config: Any) -> AgentLoop:
    return AgentLoop(
        model,
        tools,
        config=AgentLoopConfig(answer_contract="freeform", **config),
    )


# (a) parallel execution, call-order history ---------------------------------


@pytest.mark.asyncio
async def test_independent_tools_overlap_but_history_keeps_call_order() -> None:
    # Reversed delays: the first call finishes last, yet is appended first.
    delays = {STOCK: 0.3, FUND: 0.2, NEWS: 0.1}
    model = ScriptedModel([STOCK, FUND, NEWS], "done")
    tools = FakeTools(delays)
    began = time.perf_counter()
    events = await _run(_freeform(model, tools))
    elapsed = time.perf_counter() - began

    assert elapsed < 0.5, f"tools ran serially ({elapsed:.2f}s)"
    assert events[-1].type == "run.completed"
    ids = [m.tool_call_id for m in model.requests[-1] if m.role == "tool"]
    assert ids == ["call-0", "call-1", "call-2"]
    done = [e.tool for e in events if e.type == "tool.completed"]
    assert done == [STOCK, FUND, NEWS]

    serial_model = ScriptedModel([STOCK, FUND, NEWS], "done")
    serial_tools = FakeTools(delays)
    serial_started = time.perf_counter()
    await _run(_freeform(serial_model, serial_tools, concurrent_tools=False))
    assert time.perf_counter() - serial_started > 0.55
    # Model input is identical to the serial run.
    assert [m.model_dump() for m in model.requests[-1]] == [
        m.model_dump() for m in serial_model.requests[-1]
    ]


@pytest.mark.asyncio
async def test_calls_sharing_a_cache_family_stay_sequential() -> None:
    model = ScriptedModel([STOCK, TECH, FUND], "done")
    tools = FakeTools({STOCK: 0.1, TECH: 0.1, FUND: 0.1})
    await _run(_freeform(model, tools))
    assert tools.spans[TECH][0] >= tools.spans[STOCK][1]  # OHLCV lane is serial
    assert tools.spans[FUND][0] < tools.spans[STOCK][1]  # other lane overlaps


# (b) error isolation and cancellation -----------------------------------------


@pytest.mark.asyncio
async def test_one_failing_tool_does_not_cancel_siblings() -> None:
    model = ScriptedModel([STOCK, FUND, NEWS], "done")
    tools = FakeTools({STOCK: 0.05, FUND: 0.0, NEWS: 0.1}, fail={FUND})
    events = await _run(_freeform(model, tools))

    assert set(tools.spans) == {STOCK, FUND, NEWS}
    assert not tools.cancelled
    assert [e.tool for e in events if e.type == "tool.failed"] == [FUND]
    assert [e.tool for e in events if e.type == "tool.completed"] == [STOCK, NEWS]
    assert events[-1].type == "run.completed"
    assert len(_tool_messages(model)) == 3


@pytest.mark.asyncio
async def test_cancelling_the_run_cancels_in_flight_tools() -> None:
    model = ScriptedModel([STOCK, FUND], "done")
    tools = FakeTools({STOCK: 5.0, FUND: 5.0})
    loop = _freeform(model, tools)

    async def consume() -> None:
        await _run(loop)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sorted(tools.cancelled) == sorted([STOCK, FUND])


@pytest.mark.asyncio
async def test_emergency_ceiling_counts_before_launching() -> None:
    model = ScriptedModel([STOCK, FUND, NEWS], "done")
    tools = FakeTools()
    events = await _run(_freeform(model, tools, emergency_max_tool_calls=2))
    assert set(tools.spans) == {STOCK, FUND}
    assert events[-1].type == "run.completed"
    contents = _tool_messages(model) if len(model.requests) > 1 else []
    assert all("tool call skipped" not in c for c in contents[:2])


# (c)(d)(e) report fast path ------------------------------------------------------


class _Checkpoint:
    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, context: dict[str, Any]) -> RoutePlan:
        self.calls += 1
        return RoutePlan(confidence=1.0, next_action=NextAction.GENERATE_TEXT)


def _report_loop(
    model: ScriptedModel, tools: FakeTools, checkpoint: _Checkpoint, **config: Any
) -> AgentLoop:
    route = RoutePlan(
        intent="research_report",
        execution_mode=ExecutionMode.REPORT_SYNTHESIS,
        allowed_tools=set(ALL_TOOLS),
        model_tier=ModelTier.MAIN,
        requires_main_model=True,
        confidence=1.0,
    )
    return AgentLoop(
        model,
        tools,
        config=AgentLoopConfig(
            publish_reports=True,
            route_plan=route,
            resolved_ticker="ABC",
            decision_provider=checkpoint,
            **config,
        ),
    )


STANDARD = [STOCK, TECH, TSCAN, FUND, SCAN]


@pytest.mark.asyncio
async def test_fast_path_saves_one_model_call_and_keeps_evidence() -> None:
    slow_model = ScriptedModel(STANDARD, _draft())
    slow_checkpoint = _Checkpoint()
    await _run(
        _report_loop(slow_model, FakeTools(), slow_checkpoint, report_fast_path=False),
        "analyze ABC",
    )

    fast_model = ScriptedModel(STANDARD, _draft())
    fast_checkpoint = _Checkpoint()
    events = await _run(
        _report_loop(fast_model, FakeTools(), fast_checkpoint, report_fast_path=True),
        "analyze ABC",
    )

    assert len(slow_model.requests) == 2  # tool selection + synthesis
    assert len(fast_model.requests) == 1  # synthesis only
    assert slow_checkpoint.calls == 1 and fast_checkpoint.calls == 0
    assert _tool_messages(fast_model) == _tool_messages(slow_model)
    assert len(_tool_messages(fast_model)) == len(STANDARD) + 1  # + news
    assistant = next(m for m in fast_model.requests[0] if m.tool_calls)
    assert [c["function"]["name"] for c in assistant.tool_calls or []] == [
        *STANDARD,
        NEWS,
    ]
    assert events[-1].type == "run.completed"
    assert events[-1].terminal_status == "completed"


@pytest.mark.asyncio
async def test_fast_path_needs_a_resolved_report_route() -> None:
    model = ScriptedModel(STANDARD, _draft())
    loop = _report_loop(model, FakeTools(), _Checkpoint())
    object.__setattr__(loop.config, "resolved_ticker", None)
    await _run(loop, "analyze ABC")
    assert len(model.requests) == 2  # no ticker: the model chooses tools


@pytest.mark.asyncio
async def test_progress_events_are_emitted_in_order() -> None:
    model = ScriptedModel(STANDARD, _draft())
    events = await _run(
        _report_loop(model, FakeTools(), _Checkpoint(), report_fast_path=True),
        "analyze ABC",
    )
    labels = [e.label for e in events if e.type == "stage.started"]
    assert labels == [
        "Preparing research",
        "Gathering evidence",
        "Gathering evidence (1 of 6)",
        "Gathering evidence (2 of 6)",
        "Gathering evidence (3 of 6)",
        "Gathering evidence (4 of 6)",
        "Gathering evidence (5 of 6)",
        "Gathering evidence (6 of 6)",
        "Writing report",
        "Checking report",
    ]
    types = [e.type for e in events]
    assert types.index("stage.started", 2) < types.index("tool.started")
    assert types.index("tool.completed") < types.index("model.request.started")


# routing ---------------------------------------------------------------------------


class _Jev:
    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, context: dict[str, Any]) -> RoutePlan:
        self.calls += 1
        return RoutePlan(
            intent="research_report",
            execution_mode=ExecutionMode.REPORT_SYNTHESIS,
            allowed_tools=set(context["available_tools"]),
            model_tier=ModelTier.MAIN,
            requires_main_model=True,
            confidence=0.9,
        )


_CONTEXT = {"resolved_ticker": "ABC.NS", "instrument_resolution_status": "resolved"}


async def _decide(policy: RoutingPolicy, query: str, context: dict | None) -> RoutePlan:
    return await policy.decide(
        query,
        available_tools=set(ALL_TOOLS),
        available_skills={"report-synthesis"},
        conversation_context=context,
    )


@pytest.mark.asyncio
async def test_resolved_report_route_skips_the_router_call() -> None:
    jev = _Jev()
    route = await _decide(
        RoutingPolicy(jev, deterministic_report_route=True),  # type: ignore[arg-type]
        "analyze ABC",
        _CONTEXT,
    )
    assert jev.calls == 0
    assert route.execution_mode is ExecutionMode.REPORT_SYNTHESIS
    assert route.next_action is NextAction.GENERATE_TEXT
    assert route.allowed_tools == set(ALL_TOOLS)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "query", "context"),
    [
        (False, "analyze ABC", _CONTEXT),
        (True, "analyze ABC", None),
        (True, "compare ABC with XYZ", _CONTEXT),
        (True, "what is ABC", _CONTEXT),
        (True, "analyze ABC", {**_CONTEXT, "comparison_intent": True}),
    ],
)
async def test_router_still_called_when_route_is_not_deterministic(
    flag: bool, query: str, context: dict | None
) -> None:
    jev = _Jev()
    await _decide(
        RoutingPolicy(jev, deterministic_report_route=flag),  # type: ignore[arg-type]
        query,
        context,
    )
    assert jev.calls == 1


@pytest.mark.parametrize(
    ("query", "report", "comparison"),
    [
        ("please analyze RELIANCE", True, False),
        ("compare TCS and INFY", True, True),
        ("give me a report on HDFC", True, False),
        ("what is the price of ITC", False, False),
        ("can you research INFY", True, False),
    ],
)
def test_report_intent_is_shared_by_session_and_routing(
    query: str, report: bool, comparison: bool
) -> None:
    from app.services.report_intent import is_comparison, wants_report
    from finai.session_runtime import _wants_report

    assert _wants_report(query) is wants_report(query) is report
    assert is_comparison(query) is comparison


@pytest.mark.asyncio
async def test_cancelling_a_lane_cancels_its_later_futures() -> None:
    from app.core.agent_loop.tool_batch import ToolBatch
    from app.core.agent_loop.tool_execution import ToolExecutor

    tools = FakeTools({STOCK: 5.0, TECH: 5.0})
    batch = ToolBatch(ToolExecutor(tools), lambda: 30.0)
    batch.launch(
        [
            ("a", STOCK, {"ticker": "ABC.NS"}),
            ("b", TECH, {"ticker": "ABC.NS"}),
        ]
    )
    await asyncio.sleep(0.05)
    waiter = asyncio.create_task(batch.result("b"))
    await asyncio.sleep(0)
    for task in batch._tasks:
        task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(waiter, timeout=1.0)
    await batch.aclose()


# news is always part of a report -------------------------------------------------


@pytest.mark.asyncio
async def test_fast_path_runs_news_concurrently_with_other_lanes() -> None:
    tools = FakeTools(delays={STOCK: 0.3, FUND: 0.3, NEWS: 0.3})
    model = ScriptedModel(STANDARD, _draft())
    started = time.perf_counter()
    events = await _run(
        _report_loop(model, tools, _Checkpoint(), report_fast_path=True),
        "analyze ABC",
    )
    wall = time.perf_counter() - started
    assert events[-1].type == "run.completed"
    assert wall < 0.3 * 3 * 0.8  # ~max of the lanes, not their sum
    news, stock, fund = tools.spans[NEWS], tools.spans[STOCK], tools.spans[FUND]
    assert news[0] < stock[1] and news[0] < fund[1]  # news overlaps both lanes
    assert len(model.requests) == 1


def _news_payload(count: int = 10) -> dict:
    payload = dict(PAYLOAD)
    payload["data"] = [
        {
            "title": f"Headline number {i}",
            "url": f"https://news.example/{i}",
            "summary": "x" * 900,
            "published_time": "2026-09-17T00:00:00+00:00",
            "source_domain": "news.example",
        }
        for i in range(count)
    ]
    payload["provenance"] = {
        **dict(PAYLOAD["provenance"]),  # type: ignore[call-overload]
        "dataset": "news_snapshot",
        "source": "news_pipeline",
    }
    payload["sources"] = [
        {"name": "news.example", "url": f"https://news.example/{i}"}
        for i in range(count)
    ]
    return payload


@pytest.mark.asyncio
async def test_news_evidence_reaches_the_synthesis_request_not_a_stub() -> None:
    tools = FakeTools(payloads={NEWS: _news_payload()})
    model = ScriptedModel(STANDARD, _draft())
    await _run(
        _report_loop(model, tools, _Checkpoint(), report_fast_path=True),
        "analyze ABC",
    )
    news_messages = [m for m in _tool_messages(model) if "Headline number 0" in m]
    assert len(news_messages) == 1
    decoded = json.loads(news_messages[0])  # still valid JSON after fitting
    assert decoded["data"][0]["title"] == "Headline number 0"
    assert decoded["data"][0]["url"] == "https://news.example/0"
    assert decoded["provenance"]["source"] == "news_pipeline"
    assert len(news_messages[0]) <= 6_000  # survives later history compaction


@pytest.mark.asyncio
async def test_non_fast_path_report_adds_news_when_model_did_not_ask() -> None:
    tools = FakeTools()
    model = ScriptedModel([STOCK], _draft())  # model never requests news
    events = await _run(
        _report_loop(model, tools, _Checkpoint(), report_fast_path=False),
        "analyze ABC",
    )
    assert NEWS in tools.spans
    assert events[-1].type == "run.completed"
    assert any(
        item["source"] == "news" and item["status"] == "available"
        for item in events[-1].evidence_availability
    )


@pytest.mark.asyncio
async def test_news_is_not_duplicated_when_model_already_asked() -> None:
    tools = FakeTools()
    model = ScriptedModel([STOCK, NEWS], _draft())
    await _run(
        _report_loop(model, tools, _Checkpoint(), report_fast_path=False),
        "analyze ABC",
    )
    assistant = next(m for m in model.requests[-1] if m.tool_calls)
    names = [c["function"]["name"] for c in assistant.tool_calls or []]
    assert names.count(NEWS) == 1


@pytest.mark.asyncio
async def test_news_prefetch_can_be_disabled() -> None:
    tools = FakeTools()
    model = ScriptedModel([STOCK], _draft())
    await _run(
        _report_loop(
            model,
            tools,
            _Checkpoint(),
            report_fast_path=False,
            report_prefetch_news=False,
        ),
        "analyze ABC",
    )
    assert NEWS not in tools.spans


@pytest.mark.asyncio
async def test_news_failure_is_reported_as_unavailable_not_invented() -> None:
    tools = FakeTools(fail={NEWS})
    model = ScriptedModel(STANDARD, _draft())
    events = await _run(
        _report_loop(model, tools, _Checkpoint(), report_fast_path=True),
        "analyze ABC",
    )
    done = events[-1]
    assert done.type == "run.completed"
    news = [i for i in done.evidence_availability if i["source"] == "news"]
    assert news and news[0]["status"] == "unavailable"
    assert done.evidence_status == "limited"
    # The synthesis model is told news is unavailable.
    system_text = " ".join(m.content for m in model.requests[-1] if m.role == "system")
    assert "news" in system_text.lower() and "unavailable" in system_text.lower()


def test_news_tool_timeout_tracks_the_pipeline_budget() -> None:
    from app.config import settings
    from app.core.agent_loop.tool_execution import ToolExecutor

    timeout = ToolExecutor(object())._timeout_for(NEWS)
    assert timeout is not None
    assert (
        settings.NEWS_PIPELINE_TOTAL_TIMEOUT
        <= timeout
        <= settings.NEWS_PIPELINE_TOTAL_TIMEOUT + 30
    )


# X3: fast path every turn, tools off after prefetch, repair budget ---------------


class _CountingTools(FakeTools):
    def __init__(self) -> None:
        super().__init__()
        self.executed: list[str] = []

    async def execute(self, name: str, arguments: dict) -> dict:
        self.executed.append(name)
        return await super().execute(name, arguments)


@pytest.mark.asyncio
async def test_every_report_turn_in_a_session_takes_the_fast_path() -> None:
    tools = _CountingTools()
    history: list[Message] = [Message(role="user", content="analyze ABC")]
    written: list[Message] = []
    runs: list[ScriptedModel] = []
    for turn in range(2):
        model = ScriptedModel(STANDARD, _draft())
        loop = _report_loop(model, tools, _Checkpoint(), report_fast_path=True)
        events = [
            e
            async for e in loop.run(
                list(history),
                conversation_id=uuid4(),
                message_writer=written.append,
            )
        ]
        assert events[-1].type == "run.completed", turn
        assert events[-1].terminal_status == "completed", turn
        assert len(model.requests) == 1, f"turn {turn} did not take the fast path"
        fresh = [m for m in model.requests[0] if m.role == "tool"]
        assert len(fresh) >= len(STANDARD) + 1
        runs.append(model)
        history = [
            *history,
            *written,
            Message(role="user", content="analyze ABC again"),
        ]
        written.clear()
    # Fresh evidence both times: every standard tool executed once per turn.
    assert tools.executed.count(STOCK) == 2
    assert tools.executed.count(TSCAN) == 2
    ids = {
        m.tool_call_id
        for model in runs
        for m in model.requests[0]
        if m.role == "tool" and m.tool_call_id
    }
    assert len(ids) == 2 * (len(STANDARD) + 1)  # prefetch ids unique per run


@pytest.mark.asyncio
async def test_earlier_turns_do_not_block_a_new_ticker_in_the_same_session() -> None:
    tools = _CountingTools()
    first = _report_loop(
        ScriptedModel(STANDARD, _draft()), tools, _Checkpoint(), report_fast_path=True
    )
    written: list[Message] = []
    history = [Message(role="user", content="analyze ABC")]
    async for _ in first.run(
        list(history), conversation_id=uuid4(), message_writer=written.append
    ):
        pass
    second_model = ScriptedModel(STANDARD, _draft())
    second = _report_loop(second_model, tools, _Checkpoint(), report_fast_path=True)
    object.__setattr__(second.config, "resolved_ticker", "XYZ")
    seen: list[str] = []
    original = tools.execute

    async def spy(name: str, arguments: dict) -> dict:
        seen.append(arguments["ticker"])
        return await original(name, arguments)

    tools.execute = spy  # type: ignore[method-assign]
    events = [
        e
        async for e in second.run(
            [*history, *written, Message(role="user", content="analyze XYZ")],
            conversation_id=uuid4(),
        )
    ]
    assert events[-1].type == "run.completed"
    assert len(second_model.requests) == 1
    assert set(seen) == {"XYZ.NS"} or set(seen) == {"XYZ"}
    assert len(seen) == len(STANDARD) + 1


@pytest.mark.asyncio
async def test_prefetch_includes_technical_scan_and_synthesis_has_no_tools() -> None:
    tools = _CountingTools()
    model = ScriptedModel(STANDARD, _draft())
    checkpoint = _Checkpoint()
    events = await _run(
        _report_loop(model, tools, checkpoint, report_fast_path=True), "analyze ABC"
    )
    assert TSCAN in tools.executed
    assert len(model.requests) == 1
    assert model.tools_offered[-1] == []  # synthesis writes directly
    assert checkpoint.calls == 0
    assert events[-1].terminal_status == "completed"
    # The scan shares the OHLCV lane: it starts after the overview finished.
    assert tools.spans[TSCAN][0] >= tools.spans[TECH][1]


@pytest.mark.asyncio
async def test_slow_path_still_offers_tools_after_results() -> None:
    model = ScriptedModel(STANDARD, _draft())
    await _run(
        _report_loop(model, FakeTools(), _Checkpoint(), report_fast_path=False),
        "analyze ABC",
    )
    assert model.tools_offered[0]  # tool-selection round offers tools


class _BadDraftModel(ScriptedModel):
    """Always answers with unparseable text, so every report fails validation."""

    def __init__(self) -> None:
        super().__init__(STANDARD, "not a json report")


@pytest.mark.asyncio
async def test_repair_is_skipped_when_remaining_budget_is_below_the_minimum() -> None:
    tight = _BadDraftModel()
    tight_events = await _run(
        _report_loop(
            tight,
            FakeTools(),
            _Checkpoint(),
            report_fast_path=True,
            max_run_seconds=20.0,
            min_repair_seconds=30.0,
        ),
        "analyze ABC",
    )
    assert len(tight.requests) == 1  # no repair round started
    assert tight_events[-1].type == "run.completed"
    assert tight_events[-1].terminal_status == "completed_with_limited_evidence"

    roomy = _BadDraftModel()
    await _run(
        _report_loop(
            roomy,
            FakeTools(),
            _Checkpoint(),
            report_fast_path=True,
            max_run_seconds=20.0,
            min_repair_seconds=0.0,
        ),
        "analyze ABC",
    )
    assert len(roomy.requests) > 1  # repairs still run with enough budget


# report intent table -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "report"),
    [
        ("Is TCS a good buy?", True),
        ("is INFY a good investment right now", True),
        ("Should I buy RELIANCE?", True),
        ("should I sell HDFCBANK", True),
        ("Should I buy, sell or hold ITC?", True),
        ("What's the outlook for RELIANCE", True),
        ("Do a deep dive on INFY", True),
        ("deep dive into SBIN", True),
        ("fundamental and technical analysis of TCS", True),
        ("technical analysis of ITC", True),
        ("investment case for HDFCBANK", True),
        ("valuation of WIPRO", True),
        ("TCS stock analysis", True),
        ("what is the price of TCS", False),
        ("TCS quote", False),
        ("is the market open today", False),
        ("NSE market holidays this year", False),
        ("compare TCS and INFY", True),  # comparison reports stay reports
        ("should I buy TCS or INFY", False),
        ("TCS vs INFY outlook", False),
        ("hello", False),
    ],
)
def test_widened_report_detection(query: str, report: bool) -> None:
    from app.services.report_intent import is_comparison, wants_report
    from finai.session_runtime import _wants_report

    assert wants_report(query) is report
    assert _wants_report(query) is report
    if "compare" not in query:
        assert is_comparison(query) is False


@pytest.mark.asyncio
async def test_investment_question_takes_the_deterministic_report_route() -> None:
    jev = _Jev()
    route = await _decide(
        RoutingPolicy(jev, deterministic_report_route=True),  # type: ignore[arg-type]
        "Is ABC a good buy?",
        _CONTEXT,
    )
    assert jev.calls == 0
    assert route.execution_mode is ExecutionMode.REPORT_SYNTHESIS
