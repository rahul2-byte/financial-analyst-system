from uuid import uuid4

import pytest
from app.core.resources import RuntimeResources
from app.models.request_models import Message
from finai.session_runtime import ResearchRunner


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
async def test_chat_query_does_not_force_structured_report(monkeypatch) -> None:
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
