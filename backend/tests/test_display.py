"""Tests for the pure display module and its bridge ``Display`` payloads."""

from __future__ import annotations

import json
from collections.abc import Iterator
from uuid import uuid4

from app.events.models import (
    ClarificationRequested,
    EventFactory,
    ProviderCompleted,
    ProviderFailed,
    ProviderRetrying,
    ProviderStreamStarted,
    ResearchEvent,
    RunCompleted,
    RunFailed,
    RunStarted,
    SourcesUpdated,
    StageCompleted,
    StageFailed,
    StageStarted,
    TextDelta,
    ToolCompleted,
    ToolFailed,
    ToolProgress,
    ToolStarted,
)
from finai import display, plain
from finai.display import build_display, parse_clarification
from finai.state import PresentationState, reduce_event
from pydantic import TypeAdapter

from scripts.gen_reducer_goldens import GOLDENS_DIR


def _factory() -> EventFactory:
    return EventFactory(conversation_id=uuid4())


def _apply(state: PresentationState, *events: object) -> PresentationState:
    for event in events:
        state = reduce_event(state, event)  # type: ignore[arg-type]
    return state


def test_tool_started_display() -> None:
    factory = _factory()
    event = factory.make(
        ToolStarted, tool="data:fetch_fundamentals", tool_id="t1", detail="HDFCBANK.NS"
    )
    state = _apply(PresentationState(), event)

    result = build_display(event, state)

    assert result is not None
    assert result.label == "Fetching fundamentals"
    assert result.noun == "fundamentals"
    assert result.detail == "HDFCBANK.NS"
    assert result.failure_detail is None


def test_tool_completed_display() -> None:
    factory = _factory()
    event = factory.make(
        ToolCompleted, tool="data:get_technical_overview", tool_id="t1", detail="done"
    )
    state = _apply(
        PresentationState(),
        factory.make(ToolStarted, tool="data:get_technical_overview", tool_id="t1"),
        event,
    )

    result = build_display(event, state)

    assert result is not None
    assert result.label == "Fetched technical overview"
    assert result.noun == "technical overview"
    assert result.detail == "done"
    assert result.failure_detail is None


def test_tool_failed_display() -> None:
    factory = _factory()
    event = factory.make(
        ToolFailed,
        tool="data:fetch_news",
        tool_id="t1",
        message="no usable data returned",
    )
    state = _apply(
        PresentationState(),
        factory.make(ToolStarted, tool="data:fetch_news", tool_id="t1"),
        event,
    )

    result = build_display(event, state)

    assert result is not None
    assert result.label == "Fetched news"
    assert result.noun == "news"
    assert result.failure_detail == "no usable articles"
    assert result.friendly == "no usable data returned"


def test_tool_progress_display() -> None:
    factory = _factory()
    event = factory.make(
        ToolProgress,
        tool="data:fetch_news",
        tool_id="t1",
        message="reading articles",
    )
    state = _apply(
        PresentationState(),
        factory.make(ToolStarted, tool="data:fetch_news", tool_id="t1"),
        event,
    )

    result = build_display(event, state)

    assert result is not None
    assert result.label == "Fetching news"
    assert result.noun == "news"
    assert result.detail == "reading articles"


def test_stage_started_display() -> None:
    factory = _factory()
    event = factory.make(StageStarted, stage="research", label="Gathering evidence")
    state = reduce_event(PresentationState(), event)

    result = build_display(event, state)

    assert result is not None
    assert result.label == "Gathering evidence"
    assert result.detail is None


def test_stage_completed_display() -> None:
    factory = _factory()
    event = factory.make(
        StageCompleted, stage="validation", label="Checking numbers", detail="4 checks"
    )
    state = reduce_event(PresentationState(), event)

    result = build_display(event, state)

    assert result is not None
    assert result.label == "Checking numbers"
    assert result.detail == "4 checks"


def test_stage_failed_display() -> None:
    factory = _factory()
    event = factory.make(
        StageFailed,
        stage="validation",
        label="Checking numbers",
        message="validation error: Value error, bad totals [type=value_error]",
    )
    state = reduce_event(PresentationState(), event)

    result = build_display(event, state)

    assert result is not None
    assert result.label == "Checking numbers"
    assert (
        result.detail == "validation error: Value error, bad totals [type=value_error]"
    )
    assert result.friendly == "bad totals"


def test_provider_failed_display() -> None:
    factory = _factory()
    event = factory.make(
        ProviderFailed,
        provider="openrouter",
        attempts=2,
        phase="stream",
        message="upstream exploded",
        reason="timeout",
    )
    state = reduce_event(PresentationState(), event)

    result = build_display(event, state)

    assert result is not None
    assert (
        result.notice == "⚠ OpenRouter error (timeout): timed out — upstream exploded"
    )
    assert result.friendly == "upstream exploded"


def test_provider_retrying_display() -> None:
    factory = _factory()
    event = factory.make(
        ProviderRetrying,
        provider="openrouter",
        attempt=2,
        delay_ms=1500.0,
        reason="rate_limit",
    )
    state = reduce_event(PresentationState(), event)

    result = build_display(event, state)

    assert result is not None
    assert result.detail == "rate_limit · 1.5s"


def test_provider_stream_started_display() -> None:
    factory = _factory()
    event = factory.make(
        ProviderStreamStarted, provider="openrouter", attempt=1, first_byte_ms=420.0
    )
    state = reduce_event(PresentationState(), event)

    result = build_display(event, state)

    assert result is not None
    assert result.detail == "first byte 0.4s"


def test_provider_completed_display() -> None:
    factory = _factory()
    event = factory.make(
        ProviderCompleted, provider="openrouter", attempts=2, duration_ms=3100.0
    )
    state = reduce_event(PresentationState(), event)

    result = build_display(event, state)

    assert result is not None
    assert result.detail == "2 attempt(s) · 3.1s"


def test_run_failed_display_carries_friendly_error() -> None:
    factory = _factory()
    event = factory.make(
        RunFailed,
        message="validation error: Value error, totals did not reconcile [type=value_error]",
        category="internal",
    )
    state = reduce_event(PresentationState(), event)

    result = build_display(event, state)

    assert result is not None
    assert result.friendly == "totals did not reconcile"


def test_sources_updated_display() -> None:
    factory = _factory()
    event = factory.make(
        SourcesUpdated,
        sources=[
            {"title": "INFY Form 10-K", "url": "https://sec.gov/filing/1"},
            {"title": "INFY Form 10-K", "url": "https://sec.gov/filing/1"},
            {"title": "www.example.com", "url": "https://www.example.com/a"},
            {
                "name": "yfinance",
                "url": "https://finance.yahoo.com/quote/HDFCBANK.NS/history",
            },
        ],
    )
    state = reduce_event(PresentationState(), event)

    result = build_display(event, state)

    assert result is not None
    assert result.sources is not None
    assert len(result.sources) == 3
    first, second, third = result.sources
    assert first.label == "INFY Form 10-K"
    assert first.host == "sec.gov"
    assert second.label == "www.example.com"
    assert second.host is None
    assert third.label == "Yahoo Finance · price history · HDFCBANK.NS"
    assert third.host == "finance.yahoo.com"


def test_clarification_display() -> None:
    factory = _factory()
    prompt = (
        "Which company did you mean?\n"
        "- HDFCBANK.NS (NSE) HDFC BANK LTD\n"
        "- Infosys (INFY, NSE)\n"
    )
    event = factory.make(ClarificationRequested, prompt=prompt)
    state = reduce_event(PresentationState(), event)

    result = build_display(event, state)

    assert result is not None
    assert result.lines == ["Which company did you mean?"]
    assert result.candidates is not None
    assert [c.symbol for c in result.candidates] == ["HDFCBANK.NS", "INFY"]
    assert [c.name for c in result.candidates] == ["HDFC Bank Ltd", "Infosys"]
    assert [c.exchange for c in result.candidates] == ["NSE", "NSE"]


def test_run_completed_display() -> None:
    factory = _factory()
    state = _apply(
        PresentationState(),
        factory.make(ToolStarted, tool="data:fetch_fundamentals", tool_id="t1"),
        factory.make(
            SourcesUpdated,
            sources=[
                {
                    "title": "Yahoo Finance · fundamentals",
                    "url": "https://finance.yahoo.com/quote/HDFCBANK.NS/financials",
                }
            ],
        ),
        factory.make(
            ToolFailed,
            tool="data:fetch_news",
            tool_id="t2",
            message="no usable data",
        ),
    )
    event = factory.make(
        RunCompleted, terminal_status="partial", output_review="unavailable"
    )
    state = reduce_event(state, event)

    result = build_display(event, state)

    assert result is not None
    assert result.review_unavailable is True
    assert result.review_note == display.REVIEW_UNAVAILABLE_NOTE
    assert result.instrument == "HDFCBANK.NS"
    assert result.failed_nouns == ["news"]


def test_unmapped_events_have_no_display() -> None:
    factory = _factory()
    for event in (
        factory.make(TextDelta, text="hello"),
        factory.make(RunStarted, query="Analyze INFY"),
    ):
        state = reduce_event(PresentationState(), event)
        assert build_display(event, state) is None


def test_build_display_strips_escapes_and_controls_from_tool_detail() -> None:
    factory = _factory()
    event = factory.make(
        ToolStarted,
        tool="data:fetch_fundamentals",
        tool_id="t1",
        detail="bad\x1b[31mtext\x07 here",
    )
    state = reduce_event(PresentationState(), event)

    result = build_display(event, state)

    assert result is not None
    assert result.detail == "badtext here"
    assert "\x1b" not in (result.detail or "")
    assert "\x07" not in (result.detail or "")


def test_parse_clarification_both_candidate_formats() -> None:
    prompt = (
        "Pick one:\n"
        "- HDFCBANK.NS (NSE) HDFC BANK LTD\n"
        "- Infosys (INFY, NSE)\n"
        "Reply with a name.\n"
    )

    candidates, other_lines = parse_clarification(prompt)

    assert candidates == [
        ("HDFCBANK.NS", "HDFC Bank Ltd", "NSE"),
        ("INFY", "Infosys", "NSE"),
    ]
    assert other_lines == ["Pick one:", "Reply with a name."]


def test_display_and_plain_helpers_keep_their_output() -> None:
    assert display.tool_label("data:fetch_stock_data") == "Fetched stock data"
    assert display.noun("data:get_technical_overview") == "technical overview"
    assert (
        display.tool_detail(
            "data:get_technical_overview",
            "key values: close=1234.5, volume=10",
        )
        == "close ₹1234.5"
    )
    assert (
        display.failure_detail("data:fetch_news", "No usable articles for data:news")
        == "no usable articles"
    )
    assert display.short("a" * 80) == "a" * 71 + "…"
    assert display.title_name("HDFC BANK LTD") == "HDFC Bank Ltd"
    assert (
        plain.source_label(
            {"name": "yfinance", "url": "https://x/quote/TCS.NS/history"}
        )
        == "Yahoo Finance · price history · TCS.NS"
    )
    assert plain.friendly_error("Value error, bad [type=value_error]") == (
        "Value error, bad [type=value_error]"
    )
    assert (
        plain.friendly_error("validation error: Value error, bad totals [type=x]")
        == "bad totals"
    )


def test_activity_helpers_report_tool_trail_and_failures() -> None:
    factory = _factory()
    state = _apply(
        PresentationState(),
        factory.make(ToolStarted, tool="data:fetch_news", tool_id="t1"),
        factory.make(ToolFailed, tool="data:fetch_news", tool_id="t1", message="boom"),
    )

    assert display.has_tool_trail(state.activities) is True
    assert display.has_tool_trail(PresentationState().activities) is False
    assert display.failed_nouns(state.activities) == ["news"]


def test_tool_progress_running_raw_id_detail_becomes_none() -> None:
    factory = _factory()
    event = factory.make(
        ToolProgress,
        tool="data:fetch_fundamentals",
        tool_id="t1",
        message="Running data:fetch_fundamentals",
    )
    state = _apply(
        PresentationState(),
        factory.make(ToolStarted, tool="data:fetch_fundamentals", tool_id="t1"),
        event,
    )

    result = build_display(event, state)

    assert result is not None
    assert result.detail is None


def test_tool_detail_removes_raw_id_mid_sentence() -> None:
    factory = _factory()
    event = factory.make(
        ToolCompleted,
        tool="data:fetch_fundamentals",
        tool_id="t1",
        detail="Fetched data:fetch_fundamentals in 0.3s",
    )

    result = build_display(event, PresentationState())

    assert result is not None
    assert result.detail == "Fetched fundamentals in 0.3s"


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def test_build_display_golden_events_never_leak_raw_tool_ids() -> None:
    adapter: TypeAdapter[ResearchEvent] = TypeAdapter(ResearchEvent)
    goldens = sorted(GOLDENS_DIR.glob("*.json"))
    assert goldens
    for golden_path in goldens:
        payload = json.loads(golden_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "events" not in payload:
            continue
        state = PresentationState()
        for entry in payload["events"]:
            event = adapter.validate_python(entry["event"])
            state = reduce_event(state, event)
            result = build_display(event, state)
            display_dump = result.model_dump(mode="json") if result is not None else {}
            for value in _strings(display_dump):
                assert not display.RAW_ID.search(value), (
                    f"{golden_path.name}: raw id in display string {value!r}"
                )


def test_tool_label_tense_follows_event() -> None:
    assert display.tool_label("data:fetch_fundamentals") == "Fetched fundamentals"
    assert (
        display.tool_label("data:fetch_fundamentals", active=True)
        == "Fetching fundamentals"
    )
    assert display.tool_label("quant:compute_ratios", active=True) == (
        "Computing ratios"
    )
