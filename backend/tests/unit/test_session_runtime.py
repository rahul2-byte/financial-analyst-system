from uuid import uuid4

import pytest
from app.models.request_models import Message
from finai.session_runtime import ResearchRunner


@pytest.mark.asyncio
async def test_research_runner_keeps_tool_evidence_between_approval_resumes(
    monkeypatch,
) -> None:
    tool_runners = []

    class FakeLoop:
        def __init__(self, model, tool_runner, *, config):
            del model, config
            tool_runners.append(tool_runner)

        async def run(self, *args, **kwargs):
            del args, kwargs
            if False:
                yield None

    monkeypatch.setattr("finai.session_runtime.AgentLoop", FakeLoop)
    runner = ResearchRunner(object(), "guided", object(), object())
    history = [Message(role="user", content="Analyze HDFC Bank")]

    for _ in range(2):
        async for _event in runner.stream(history, "yes", uuid4()):
            pass

    assert tool_runners[0] is tool_runners[1]
