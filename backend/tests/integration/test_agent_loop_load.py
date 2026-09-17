import asyncio
import time
from uuid import uuid4

import pytest
from app.core.agent_loop import AgentLoop
from app.models.request_models import Message


class _Model:
    def generate_stream(self, messages, model, **kwargs):
        del messages, model, kwargs

        async def stream():
            yield {"event": "token", "data": "ready"}

        return stream()


class _SlowModel:
    def generate_stream(self, messages, model, **kwargs):
        del messages, model, kwargs

        async def stream():
            await asyncio.sleep(60)
            yield {"event": "token", "data": "never"}

        return stream()


class _Tools:
    def definitions(self):
        return []

    async def execute(self, name, arguments):
        del name, arguments
        return {"success": True}


async def _collect(loop: AgentLoop) -> list:
    return [
        event
        async for event in loop.run(
            [Message(role="user", content="hello")],
            conversation_id=uuid4(),
        )
    ]


@pytest.mark.asyncio
async def test_agent_loop_handles_cancellation_without_leaking_the_task() -> None:
    task = asyncio.create_task(_collect(AgentLoop(_SlowModel(), _Tools())))
    await asyncio.sleep(0)
    task.cancel()

    events = await task

    assert events[-1].type == "run.cancelled"


@pytest.mark.asyncio
async def test_agent_loop_load_measurement_runs_bounded_replay_workload() -> None:
    started = time.perf_counter()
    completed = 0
    for _ in range(25):
        events = await _collect(AgentLoop(_Model(), _Tools()))
        completed += events[-1].type == "run.completed"

    elapsed_ms = (time.perf_counter() - started) * 1000

    assert completed == 25
    assert 0 <= elapsed_ms < 5_000
