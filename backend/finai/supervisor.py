"""Reliability boundary for a terminal research run."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from app.events.models import EventFactory, ResearchEvent, RunFailed


async def supervise(
    events: AsyncIterator[ResearchEvent], *, conversation_id: UUID
) -> AsyncIterator[ResearchEvent]:
    """Guarantee a visible terminal outcome for a non-cancelled stream."""
    factory = EventFactory(conversation_id)
    terminal = False
    run_id = factory.run_id
    sequence = 0
    try:
        async for event in events:
            run_id = event.meta.run_id
            sequence = event.meta.sequence
            if event.type in {
                "run.completed",
                "run.failed",
                "run.cancelled",
                "approval.requested",
                "clarification.requested",
            }:
                terminal = True
            yield event
    except Exception as exc:  # noqa: BLE001 - supervisor is the run boundary
        yield EventFactory(conversation_id, run_id=run_id, sequence=sequence).make(
            RunFailed, message=f"Research stopped unexpectedly: {exc}"
        )
        return
    if not terminal:
        yield EventFactory(conversation_id, run_id=run_id, sequence=sequence).make(
            RunFailed,
            message="Research stream ended before a terminal result was produced.",
            category="stream",
        )
