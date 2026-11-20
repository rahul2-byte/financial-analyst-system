"""Replayable event fixture shaped like a real HDFC Bank research run.

The real run emitted ``response.delta`` with sequence 1330 *after*
``model.response.completed`` with sequence 1361, so the report arrived with a
lower sequence than an event the UI had already applied.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.events.models import EventMeta, ResearchEvent
from pydantic import TypeAdapter

_PATH = Path(__file__).with_name("hdfc_run_events.json")
_ADAPTER: TypeAdapter[ResearchEvent] = TypeAdapter(ResearchEvent)


def hdfc_run_events() -> list[ResearchEvent]:
    events: list[ResearchEvent] = []
    for raw in json.loads(_PATH.read_text(encoding="utf-8")):
        raw["meta"] = EventMeta(
            event_id=uuid4(),
            run_id=UUID(raw["meta"]["run_id"]),
            conversation_id=UUID(raw["meta"]["conversation_id"]),
            sequence=raw["meta"]["sequence"],
            occurred_at=datetime.now(UTC),
        ).model_dump()
        events.append(_ADAPTER.validate_python(raw))
    return events


def chat_only_events(
    reply: str = "Hello! Ask me about an NSE or BSE company.",
) -> list[ResearchEvent]:
    """A chat reply: the runtime still emits a 'Preparing research' stage."""
    from app.events.models import (
        EventFactory,
        RunCompleted,
        RunStarted,
        StageStarted,
        TextDelta,
    )

    factory = EventFactory(uuid4())
    return [
        factory.make(RunStarted, query="Hello"),
        factory.make(StageStarted, stage="agent", label="Preparing research"),
        factory.make(TextDelta, text=reply),
        factory.make(RunCompleted, terminal_status="success", duration_ms=1800.0),
    ]


PARTIAL_REPORT = (
    "## Research report\n\n"
    "### Executive summary\n"
    "HDFC Bank closed at **₹846.0**, about 11% above its 200-day average.\n\n"
    "### Limits\n"
    "Recent news could not be retrieved, so this view rests on price and "
    "fundamentals only.\n"
)


def partial_run_events() -> list[ResearchEvent]:
    """Two tools succeed, news fails: a partial run with a plain-words footer reason."""
    from app.events.models import (
        EventFactory,
        RunCompleted,
        RunStarted,
        SourcesUpdated,
        StageStarted,
        TextDelta,
        ToolCompleted,
        ToolFailed,
        ToolStarted,
    )

    factory = EventFactory(uuid4())
    events: list[ResearchEvent] = [
        factory.make(RunStarted, query="HDFCBANK"),
        factory.make(StageStarted, stage="agent", label="Preparing research"),
    ]
    for tool, detail in (
        ("data:fetch_fundamentals", "received 17 fields"),
        ("analysis:get_technical_overview", "key values: close=846.0, RSI_14=77.9"),
    ):
        events.append(factory.make(ToolStarted, tool=tool, tool_id=tool))
        events.append(
            factory.make(ToolCompleted, tool=tool, tool_id=tool, detail=detail)
        )
    events.append(factory.make(ToolStarted, tool="news:fetch_news", tool_id="n1"))
    events.append(
        factory.make(
            ToolFailed,
            tool="news:fetch_news",
            tool_id="n1",
            message="No usable evidence returned for news:fetch_news",
        )
    )
    events.append(
        factory.make(
            SourcesUpdated,
            sources=[
                {"name": "upstox", "url": "https://api.upstox.com"},
                {
                    "name": "Yahoo Finance",
                    "url": "https://finance.yahoo.com/quote/HDFCBANK.NS/",
                },
            ],
        )
    )
    events.append(factory.make(TextDelta, text=PARTIAL_REPORT))
    events.append(
        factory.make(
            RunCompleted,
            terminal_status="completed_with_limited_evidence",
            duration_ms=58100.0,
        )
    )
    return events
