from uuid import uuid4

import pytest
from app.events.models import ApprovalRequested, EventFactory, RunStarted
from finai.supervisor import supervise


async def _events(*items):
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_supervisor_marks_premature_stream_end_as_failure() -> None:
    factory = EventFactory(uuid4())
    events = [
        event
        async for event in supervise(
            _events(factory.make(RunStarted, query="INFY")),
            conversation_id=factory.conversation_id,
        )
    ]

    assert events[-1].type == "run.failed"
    assert events[-1].category == "stream"
    assert events[-1].meta.run_id == events[0].meta.run_id
    assert events[-1].meta.sequence > events[0].meta.sequence


@pytest.mark.asyncio
async def test_supervisor_converts_iterator_error_to_failure() -> None:
    async def broken():
        raise TimeoutError("provider timeout")
        yield  # pragma: no cover

    events = [event async for event in supervise(broken(), conversation_id=uuid4())]

    assert events[-1].type == "run.failed"
    assert "provider timeout" in events[-1].message


@pytest.mark.asyncio
async def test_supervisor_accepts_waiting_for_approval_as_terminal() -> None:
    factory = EventFactory(uuid4())
    events = [
        event
        async for event in supervise(
            _events(
                factory.make(RunStarted, query="Analyze INFY"),
                factory.make(ApprovalRequested, prompt="Approve plan?"),
            ),
            conversation_id=factory.conversation_id,
        )
    ]

    assert events[-1].type == "approval.requested"
