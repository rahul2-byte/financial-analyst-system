import asyncio
from uuid import uuid4

import pytest
from app.config import settings
from app.core.resources import RuntimeResources
from app.models.request_models import Message
from app.models.routing import ExecutionMode, ModelTier, NextAction, RoutePlan
from finai.session_runtime import ResearchRunner, _model_for_route, _wants_report


def test_small_route_selects_luna(monkeypatch) -> None:
    monkeypatch.setattr(settings, "FINAI_CHATGPT_CODEX_LUNA_MODEL", "luna-test")

    route = RoutePlan(model_tier=ModelTier.SMALL)

    assert _model_for_route(route, "chatgpt_codex") == "luna-test"


def test_report_intent_accepts_polite_analysis_requests() -> None:
    assert _wants_report("I want you to analyse HDFC Bank") is True
    assert _wants_report("Please analyze INFY") is True
    assert _wants_report("Could you research the banking sector?") is True
    assert _wants_report("Analsye the HDFC BANK stock for the last 1 year") is True


def test_report_intent_does_not_promote_ordinary_questions() -> None:
    assert _wants_report("What is HDFC Bank's current price?") is False
    assert _wants_report("") is False


@pytest.mark.asyncio
async def test_research_runner_keeps_tool_evidence_between_approval_resumes(
    monkeypatch,
) -> None:
    tool_runners = []

    class FakeLoop:
        def __init__(self, model, tool_runner, *, config, skill_registry=None):
            del model, config, skill_registry
            tool_runners.append(tool_runner)

        async def run(self, *args, **kwargs):
            del args, kwargs
            if False:
                yield None

    monkeypatch.setattr("finai.session_runtime.AgentLoop", FakeLoop)
    runner = ResearchRunner(
        RuntimeResources(llm_service=object(), yf_fetcher=object()), "guided"
    )
    history = [Message(role="user", content="Analyze HDFC Bank")]

    for _ in range(2):
        async for _event in runner.stream(history, "yes", uuid4()):
            pass

    assert tool_runners[0] is tool_runners[1]


@pytest.mark.asyncio
async def test_cli_runner_uses_bundled_skill_registry(monkeypatch) -> None:
    registries = []

    class FakeLoop:
        def __init__(self, model, tool_runner, *, config, skill_registry=None):
            del model, tool_runner, config
            registries.append(skill_registry)

        async def run(self, *args, **kwargs):
            del args, kwargs
            if False:
                yield None

    monkeypatch.setattr("finai.session_runtime.AgentLoop", FakeLoop)
    runner = ResearchRunner(
        RuntimeResources(llm_service=object(), yf_fetcher=object()), "guided"
    )
    async for _event in runner.stream(
        [Message(role="user", content="Analyze HDFC Bank")],
        "Analyze HDFC Bank",
        uuid4(),
    ):
        pass

    assert registries and registries[0] is not None


@pytest.mark.asyncio
async def test_runner_passes_conversation_context_to_router(monkeypatch) -> None:
    captured = {}

    class Policy:
        async def decide(self, query, **kwargs):
            captured.update(kwargs)
            return RoutePlan(
                intent="general_question",
                execution_mode=ExecutionMode.MODEL_ANSWER,
                model_tier=ModelTier.SMALL,
                confidence=0.9,
            )

    class FakeLoop:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        async def run(self, *args, **kwargs):
            del args, kwargs
            if False:
                yield None

    runner = ResearchRunner(
        RuntimeResources(
            llm_service=object(), yf_fetcher=object(), routing_policy=Policy()
        ),
        "guided",
    )
    monkeypatch.setattr("finai.session_runtime.AgentLoop", FakeLoop)
    async for _event in runner.stream(
        [
            Message(role="user", content="Analyse HDFC Bank."),
            Message(role="assistant", content="The HDFC Bank report is ready."),
        ],
        "Compare this with other stocks in the sector.",
        uuid4(),
    ):
        pass

    context = captured["conversation_context"]
    assert context["is_follow_up"] is True
    assert "HDFC Bank" in context["resolved_entities"]


@pytest.mark.asyncio
async def test_runner_resolves_bare_hdfc_bank_and_passes_ticker_context(monkeypatch) -> None:
    captured = {}

    class Upstox:
        def resolve_instrument(self, query):
            assert query == "HDFC"
            return [{"trading_symbol": "HDFCBANK", "short_name": "HDFC Bank"}]

    class Policy:
        async def decide(self, query, **kwargs):
            captured.update(kwargs)
            return RoutePlan(
                intent="research_report",
                execution_mode=ExecutionMode.REPORT_SYNTHESIS,
                model_tier=ModelTier.MAIN,
                confidence=0.9,
            )

    class FakeLoop:
        def __init__(self, *args, **kwargs):
            captured["config"] = kwargs["config"]

        async def run(self, *args, **kwargs):
            del args, kwargs
            if False:
                yield None

    monkeypatch.setattr("finai.session_runtime.AgentLoop", FakeLoop)
    runner = ResearchRunner(
        RuntimeResources(
            llm_service=object(),
            yf_fetcher=object(),
            upstox_fetcher=Upstox(),
            routing_policy=Policy(),
        ),
        "guided",
    )
    query = "Analyse the HDFC BANK stock for the last 1 year"
    async for _event in runner.stream(
        [Message(role="user", content=query)], query, uuid4()
    ):
        pass

    assert captured["conversation_context"]["resolved_ticker"] == "HDFCBANK.NS"
    assert captured["config"].resolved_ticker == "HDFCBANK.NS"


@pytest.mark.asyncio
async def test_runner_reuses_resolved_ticker_for_follow_up(monkeypatch) -> None:
    contexts = []

    class Upstox:
        def resolve_instrument(self, query):
            return [{"trading_symbol": "HDFCBANK", "short_name": "HDFC Bank"}]

    class Policy:
        async def decide(self, query, **kwargs):
            contexts.append(kwargs["conversation_context"])
            return RoutePlan(
                intent="general_question",
                execution_mode=ExecutionMode.MODEL_ANSWER,
                model_tier=ModelTier.SMALL,
                confidence=0.9,
            )

    class FakeLoop:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        async def run(self, *args, **kwargs):
            del args, kwargs
            if False:
                yield None

    monkeypatch.setattr("finai.session_runtime.AgentLoop", FakeLoop)
    runner = ResearchRunner(
        RuntimeResources(
            llm_service=object(),
            yf_fetcher=object(),
            upstox_fetcher=Upstox(),
            routing_policy=Policy(),
        ),
        "guided",
    )
    conversation_id = uuid4()
    history = [Message(role="user", content="Analyse the HDFC BANK stock")]
    async for _event in runner.stream(history, history[0].content, conversation_id):
        pass
    history.append(Message(role="assistant", content="Continuing with HDFCBANK.NS."))
    async for _event in runner.stream(
        history, "Use any exchange you want", conversation_id
    ):
        pass

    assert contexts[-1]["resolved_ticker"] == "HDFCBANK.NS"


@pytest.mark.asyncio
async def test_plain_query_does_not_force_structured_report(monkeypatch) -> None:
    configs = []

    class FakeLoop:
        def __init__(self, model, tool_runner, *, config, skill_registry=None):
            del model, tool_runner, skill_registry
            configs.append(config)

        async def run(self, *args, **kwargs):
            del args, kwargs
            if False:
                yield None

    monkeypatch.setattr("finai.session_runtime.AgentLoop", FakeLoop)
    runner = ResearchRunner(
        RuntimeResources(llm_service=object(), yf_fetcher=object()), "guided"
    )
    async for _event in runner.stream(
        [Message(role="user", content="Hello")], "Hello", uuid4()
    ):
        pass
    assert configs[0].publish_reports is False


@pytest.mark.asyncio
async def test_analysis_query_uses_report_validation(monkeypatch) -> None:
    configs = []

    class FakeLoop:
        def __init__(self, model, tool_runner, *, config, skill_registry=None):
            del model, tool_runner, skill_registry
            configs.append(config)

        async def run(self, *args, **kwargs):
            del args, kwargs
            if False:
                yield None

    monkeypatch.setattr("finai.session_runtime.AgentLoop", FakeLoop)
    runner = ResearchRunner(
        RuntimeResources(llm_service=object(), yf_fetcher=object()), "guided"
    )
    async for _event in runner.stream(
        [Message(role="user", content="Analyse HDFC Bank")],
        "Analyse HDFC Bank",
        uuid4(),
    ):
        pass
    assert configs[0].publish_reports is True


def test_runner_executes_direct_market_route_without_model_call() -> None:
    class Model:
        def generate_stream(self, *args, **kwargs):
            raise AssertionError("model should not run for a direct route")

    class Fetcher:
        def fetch_stock_price(self, ticker, period, interval):
            return {
                "ticker": ticker,
                "period": period,
                "interval": interval,
                "data": [
                    {"date": "2026-01-01", "close": 100},
                    {"date": "2026-01-02", "close": 110},
                ],
                "provenance": {
                    "source": "test",
                    "observed_at": "2026-01-02T00:00:00+00:00",
                },
            }

    class Policy:
        async def decide(self, *args, **kwargs):
            return RoutePlan(
                intent="market_lookup",
                execution_mode=ExecutionMode.TOOL_ONLY,
                required_tools=["data:fetch_stock_data"],
                allowed_tools={"data:fetch_stock_data"},
                model_tier=ModelTier.NONE,
                confidence=1.0,
            )

    async def scenario():
        resources = RuntimeResources(
            llm_service=Model(), yf_fetcher=Fetcher(), routing_policy=Policy()
        )
        runner = ResearchRunner(resources, "guided")
        return [
            event
            async for event in runner.stream(
                [Message(role="user", content="What is the current price of TCS?")],
                "What is the current price of TCS?",
                uuid4(),
            )
        ]

    events = asyncio.run(scenario())

    response = next(event.text for event in events if event.type == "response.delta")
    assert "TCS" in response
    assert "observed_at" in response
    assert '"source": "test"' in response
    assert events[-1].type == "run.completed"


def test_runner_executes_market_status_route_without_instrument_resolution() -> None:
    class Model:
        def generate_stream(self, *args, **kwargs):
            raise AssertionError("model should not run for a direct route")

    class Upstox:
        def resolve_instrument(self, query):
            raise AssertionError(f"status lookup must not resolve an instrument: {query}")

        def fetch_market_status(self, exchange):
            return {"exchange": exchange, "status": "NORMAL_OPEN", "last_updated": 1}

    class Policy:
        async def decide(self, *args, **kwargs):
            return RoutePlan(
                intent="market_status",
                execution_mode=ExecutionMode.TOOL_ONLY,
                required_tools=["data:fetch_market_status"],
                allowed_tools={"data:fetch_market_status"},
                model_tier=ModelTier.NONE,
                confidence=1.0,
            )

    async def scenario():
        runner = ResearchRunner(
            RuntimeResources(
                llm_service=Model(),
                yf_fetcher=object(),
                upstox_fetcher=Upstox(),
                routing_policy=Policy(),
            ),
            "guided",
        )
        return [
            event
            async for event in runner.stream(
                [Message(role="user", content="Is NSE open?")],
                "Is NSE open?",
                uuid4(),
            )
        ]

    events = asyncio.run(scenario())
    response = next(event.text for event in events if event.type == "response.delta")
    assert "NORMAL_OPEN" in response
    assert events[-1].terminal_status == "completed"


def test_runner_direct_tool_failure_has_one_insufficient_data_terminal_event() -> None:
    class Model:
        def generate_stream(self, *args, **kwargs):
            raise AssertionError("model should not run for a direct route")

    class Fetcher:
        def fetch_stock_price(self, ticker, period, interval):
            del ticker, period, interval
            return {"error": "No data found"}

    class Policy:
        async def decide(self, *args, **kwargs):
            return RoutePlan(
                intent="market_lookup",
                execution_mode=ExecutionMode.TOOL_ONLY,
                required_tools=["data:fetch_stock_data"],
                allowed_tools={"data:fetch_stock_data"},
                model_tier=ModelTier.NONE,
                confidence=1.0,
            )

    async def scenario():
        runner = ResearchRunner(
            RuntimeResources(
                llm_service=Model(), yf_fetcher=Fetcher(), routing_policy=Policy()
            ),
            "guided",
        )
        return [
            event
            async for event in runner.stream(
                [Message(role="user", content="What is the current price of TCS?")],
                "What is the current price of TCS?",
                uuid4(),
            )
        ]

    events = asyncio.run(scenario())
    completed = [event for event in events if event.type == "run.completed"]
    assert len(completed) == 1
    assert completed[0].terminal_status == "insufficient_data"


@pytest.mark.asyncio
async def test_runner_clarifies_ambiguous_provider_instrument() -> None:
    class Model:
        def generate_stream(self, *args, **kwargs):
            raise AssertionError("model should not run for an ambiguous lookup")

    class Fetcher:
        def fetch_stock_price(self, *args, **kwargs):
            raise AssertionError("provider lookup should stop before price fetch")

    class Upstox:
        def resolve_instrument(self, query):
            assert query == "TATA"
            return [
                {"trading_symbol": "TATAMOTORS"},
                {"trading_symbol": "TATASTEEL"},
            ]

    class Policy:
        async def decide(self, *args, **kwargs):
            return RoutePlan(
                intent="market_lookup",
                execution_mode=ExecutionMode.TOOL_ONLY,
                required_tools=["data:fetch_stock_data"],
                allowed_tools={"data:fetch_stock_data"},
                model_tier=ModelTier.NONE,
                confidence=1.0,
            )

    runner = ResearchRunner(
        RuntimeResources(
            llm_service=Model(),
            yf_fetcher=Fetcher(),
            upstox_fetcher=Upstox(),
            routing_policy=Policy(),
        ),
        "guided",
    )
    events = [
        event
        async for event in runner.stream(
            [Message(role="user", content="What is the current price of Tata stock?")],
            "What is the current price of Tata stock?",
            uuid4(),
        )
    ]

    assert any(event.type == "clarification.requested" for event in events)
    assert events[-1].terminal_status == "awaiting_clarification"


@pytest.mark.asyncio
async def test_runner_pauses_for_initial_clarification_without_model_call() -> None:
    class Model:
        def generate_stream(self, *args, **kwargs):
            raise AssertionError("model should not run for a clarification route")

    class Policy:
        async def decide(self, *args, **kwargs):
            return RoutePlan(
                intent="clarification",
                execution_mode=ExecutionMode.DETERMINISTIC,
                model_tier=ModelTier.NONE,
                next_action=NextAction.ASK_CLARIFICATION,
                confidence=0.9,
                reason="The ticker is ambiguous.",
            )

    async def scenario():
        resources = RuntimeResources(
            llm_service=Model(), yf_fetcher=object(), routing_policy=Policy()
        )
        runner = ResearchRunner(resources, "guided")
        return [
            event
            async for event in runner.stream(
                [Message(role="user", content="Analyse this company")],
                "Analyse this company",
                uuid4(),
            )
        ]

    events = await scenario()

    assert any(event.type == "clarification.requested" for event in events)
    assert events[-1].type == "run.completed"
    assert events[-1].terminal_status == "awaiting_clarification"
