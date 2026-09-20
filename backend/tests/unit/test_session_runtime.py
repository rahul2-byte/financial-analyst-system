import asyncio
from uuid import uuid4

import pytest
from app.core.resources import RuntimeResources
from app.models.request_models import Message
from app.models.routing import ExecutionMode, ModelTier, RoutePlan
from finai.session_runtime import ResearchRunner, _wants_report


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
                "provenance": {"source": "test"},
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

    assert any(
        event.type == "response.delta" and "TCS" in event.text for event in events
    )
    assert events[-1].type == "run.completed"
