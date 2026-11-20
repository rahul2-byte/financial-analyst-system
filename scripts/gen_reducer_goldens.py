"""Generate the TS reducer golden files under ``frontend/test/goldens``.

Usage: ``uv run --offline python scripts/gen_reducer_goldens.py``.

The committed goldens are checked for freshness by
``backend/tests/test_reducer_goldens.py``: regenerate into a temp directory and
compare byte-for-byte.
"""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid5

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _entry in (_REPO_ROOT, _REPO_ROOT / "backend"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from app.events.models import (  # noqa: E402
    ClarificationRequested,
    EventFactory,
    ProviderAttemptStarted,
    ProviderFailed,
    ProviderRetrying,
    ResearchEvent,
    RunCancelled,
    RunCompleted,
    RunFailed,
    RunStarted,
    SourcesUpdated,
    StageStarted,
    TextDelta,
    ToolCompleted,
    ToolFailed,
    ToolStarted,
)
from finai.display import build_display  # noqa: E402
from finai.safety import sanitize_terminal_text  # noqa: E402
from finai.state import PresentationState, reduce_event  # noqa: E402
from tests.fixtures.hdfc_run import chat_only_events, hdfc_run_events  # noqa: E402

GOLDENS_DIR = _REPO_ROOT / "frontend" / "test" / "goldens"
_FIXED_TIME = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

GOLDEN_NAMES: tuple[str, ...] = (
    "chat_only",
    "clarification",
    "cancelled",
    "failed",
    "hdfc_run",
    "out_of_order_duplicates",
    "provider_retry_then_failure",
    "review_unavailable",
    "sources_overlap",
    "tool_failure_pydantic",
)


def _factory(name: str) -> EventFactory:
    conversation_id = uuid5(uuid.NAMESPACE_DNS, f"finai-golden:{name}:conversation")
    run_id = uuid5(uuid.NAMESPACE_DNS, f"finai-golden:{name}:run")
    return EventFactory(conversation_id, run_id=run_id)


def _normalized(events: list[ResearchEvent], name: str) -> list[ResearchEvent]:
    """Rewrite meta to fixed UUIDs/timestamps so goldens are byte-stable."""
    run_id = uuid5(uuid.NAMESPACE_DNS, f"finai-golden:{name}:run")
    conversation_id = uuid5(uuid.NAMESPACE_DNS, f"finai-golden:{name}:conversation")
    out: list[ResearchEvent] = []
    for event in events:
        meta = event.meta.model_copy(
            update={
                "event_id": uuid5(
                    uuid.NAMESPACE_DNS, f"finai-golden:{name}:{event.meta.sequence}"
                ),
                "run_id": run_id,
                "conversation_id": conversation_id,
                "occurred_at": _FIXED_TIME,
            }
        )
        out.append(event.model_copy(update={"meta": meta}))
    return out


def _out_of_order_duplicates() -> list[ResearchEvent]:
    factory = _factory("out_of_order_duplicates")
    e1 = factory.make(RunStarted, query="HDFC Bank")
    e2 = factory.make(StageStarted, stage="agent", label="Preparing research")
    e3 = factory.make(ToolStarted, tool="data:fetch_fundamentals", tool_id="t1")
    e4 = factory.make(
        ToolCompleted, tool="data:fetch_fundamentals", tool_id="t1", detail="ok"
    )
    e5 = factory.make(
        ToolCompleted, tool="data:fetch_fundamentals", tool_id="t1", detail="ok"
    )
    e6 = factory.make(RunCompleted, terminal_status="completed", duration_ms=100.0)
    # Stream order: e4 (sequence 4) arrives before e3 (sequence 3) -> out of
    # order; e3 is repeated -> duplicate.
    return [e1, e2, e4, e3, e3, e5, e6]


def _provider_retry_then_failure() -> list[ResearchEvent]:
    factory = _factory("provider_retry_then_failure")
    e1 = factory.make(RunStarted, query="HDFC Bank")
    e2 = factory.make(StageStarted, stage="agent", label="Preparing research")
    e3 = factory.make(ProviderAttemptStarted, provider="openrouter", attempt=1)
    e4 = factory.make(
        ProviderRetrying,
        provider="openrouter",
        attempt=2,
        status_code=429,
        delay_ms=5000.0,
        reason="rate_limit",
    )
    e5 = factory.make(
        ProviderFailed,
        provider="openrouter",
        attempts=3,
        phase="stream",
        message="Rate limited: slow down and retry",
        status_code=429,
        reason="rate_limit",
    )
    e6 = factory.make(RunFailed, message="Provider stream failed: rate limited")
    return [e1, e2, e3, e4, e5, e6]


def _tool_failure_pydantic() -> list[ResearchEvent]:
    factory = _factory("tool_failure_pydantic")
    message = (
        "1 validation error for StockData\n"
        "Value error, close must be a number [type=value_error, input_value='abc', "
        "input_type=str]\n"
        "  For further information visit https://errors.pydantic.dev/2.9/v/value_error"
    )
    e1 = factory.make(RunStarted, query="HDFC Bank")
    e2 = factory.make(StageStarted, stage="agent", label="Preparing research")
    e3 = factory.make(ToolStarted, tool="data:fetch_fundamentals", tool_id="t1")
    e4 = factory.make(
        ToolFailed, tool="data:fetch_fundamentals", tool_id="t1", message=message
    )
    e5 = factory.make(
        RunCompleted, terminal_status="completed_with_limited_evidence", duration_ms=9000.0
    )
    return [e1, e2, e3, e4, e5]


def _sources_overlap() -> list[ResearchEvent]:
    factory = _factory("sources_overlap")
    first = [
        {"name": "upstox", "url": "https://api.upstox.com"},
        {
            "name": "Yahoo Finance",
            "url": "https://finance.yahoo.com/quote/HDFCBANK.NS/",
        },
    ]
    second = [
        {"name": "upstox", "url": "https://api.upstox.com"},
        {
            "name": "Yahoo Finance",
            "url": "https://finance.yahoo.com/quote/HDFCBANK.NS/",
        },
        {"name": "NSE", "url": "https://www.nseindia.com/quote/HDFCBANK"},
    ]
    e1 = factory.make(RunStarted, query="HDFC Bank")
    e2 = factory.make(SourcesUpdated, sources=first)
    e3 = factory.make(SourcesUpdated, sources=second)
    e4 = factory.make(RunCompleted, terminal_status="completed", duration_ms=4200.0)
    return [e1, e2, e3, e4]


def _clarification() -> list[ResearchEvent]:
    factory = _factory("clarification")
    prompt = (
        "Please pick a company:\n"
        "- HDFCBANK.NS (NSE) HDFC Bank\n"
        "- ICICIBANK.NS (NSE) ICICI Bank\n"
        "Or answer in your own words."
    )
    e1 = factory.make(RunStarted, query="Which bank?")
    e2 = factory.make(ClarificationRequested, prompt=prompt)
    e3 = factory.make(
        RunCompleted, terminal_status="awaiting_clarification", duration_ms=2500.0
    )
    return [e1, e2, e3]


def _cancelled() -> list[ResearchEvent]:
    factory = _factory("cancelled")
    e1 = factory.make(RunStarted, query="HDFC Bank")
    e2 = factory.make(StageStarted, stage="agent", label="Preparing research")
    e3 = factory.make(ToolStarted, tool="data:fetch_fundamentals", tool_id="t1")
    e4 = factory.make(RunCancelled)
    return [e1, e2, e3, e4]


def _failed() -> list[ResearchEvent]:
    factory = _factory("failed")
    e1 = factory.make(RunStarted, query="HDFC Bank")
    e2 = factory.make(StageStarted, stage="agent", label="Preparing research")
    e3 = factory.make(ToolStarted, tool="data:fetch_fundamentals", tool_id="t1")
    e4 = factory.make(
        ToolFailed,
        tool="data:fetch_fundamentals",
        tool_id="t1",
        message="No usable data returned for data:fetch_fundamentals",
    )
    e5 = factory.make(RunFailed, message="Provider returned an error: quota exceeded")
    return [e1, e2, e3, e4, e5]


def _review_unavailable() -> list[ResearchEvent]:
    factory = _factory("review_unavailable")
    e1 = factory.make(RunStarted, query="HDFC Bank")
    e2 = factory.make(StageStarted, stage="agent", label="Preparing research")
    e3 = factory.make(TextDelta, text="Partial report text")
    e4 = factory.make(RunCompleted, terminal_status="completed", output_review="unavailable")
    return [e1, e2, e3, e4]


def _streams() -> dict[str, list[ResearchEvent]]:
    return {
        "hdfc_run": _normalized(hdfc_run_events(), "hdfc_run"),
        "out_of_order_duplicates": _normalized(
            _out_of_order_duplicates(), "out_of_order_duplicates"
        ),
        "provider_retry_then_failure": _normalized(
            _provider_retry_then_failure(), "provider_retry_then_failure"
        ),
        "tool_failure_pydantic": _normalized(
            _tool_failure_pydantic(), "tool_failure_pydantic"
        ),
        "sources_overlap": _normalized(_sources_overlap(), "sources_overlap"),
        "clarification": _normalized(_clarification(), "clarification"),
        "cancelled": _normalized(_cancelled(), "cancelled"),
        "failed": _normalized(_failed(), "failed"),
        "review_unavailable": _normalized(_review_unavailable(), "review_unavailable"),
        "chat_only": _normalized(chat_only_events(), "chat_only"),
    }


def _state_to_json(state: PresentationState) -> dict[str, Any]:
    """Serialize ``PresentationState`` with sorted keys, JSON-safe values."""
    activities = {
        key: {
            "label": activity.label,
            "status": activity.status,
            "detail": activity.detail,
        }
        for key, activity in sorted(state.activities.items())
    }
    return {
        "phase": state.phase.value,
        "run_id": str(state.run_id) if state.run_id is not None else None,
        "query": state.query,
        "response_text": state.response_text,
        "response_delta_count": state.response_delta_count,
        "terminal_status": state.terminal_status,
        "error": state.error,
        "latest_sequence": state.latest_sequence,
        "last_event_type": state.last_event_type,
        "current_operation": state.current_operation,
        "active_tools": list(state.active_tools),
        "activities": activities,
        "sources": [dict(source) for source in state.sources],
        "seen_sequences": sorted(state.seen_sequences),
    }


def render_golden(events: Sequence[ResearchEvent]) -> dict[str, Any]:
    """Render one golden: every event with its display plus a snapshot per event."""
    entries: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    state = PresentationState()
    for event in events:
        state = reduce_event(state, event)
        display = build_display(event, state)
        entries.append(
            {
                "event": event.model_dump(mode="json"),
                "display": (
                    display.model_dump(mode="json") if display is not None else None
                ),
            }
        )
        snapshots.append(
            {"after_sequence": event.meta.sequence, "state": _state_to_json(state)}
        )
    return {
        "events": entries,
        "snapshots": snapshots,
        "final": _state_to_json(state),
    }


def sanitize_cases() -> list[dict[str, str]]:
    """Pin ``sanitize_terminal_text`` on ESC sequences, controls and tabs/newlines."""
    cases = [
        "\x1b[31mred\x1b[0m",
        "\x1b[2J\x1b[Hstatus: running",
        "\x1b]8;;https://example.com\x07link text\x1b]8;;\x07",
        "a\x00\x07\x0b\x0c\x0e\x1f\x7fz",
        "\x85\x9c",
        "line one\nline two\r\nline three\ttab",
        "unicode ✓ ₹ stays",
    ]
    return [
        {"input": case, "output": sanitize_terminal_text(case)} for case in cases
    ]


def _dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_golden(out_dir: Path | str = GOLDENS_DIR) -> list[Path]:
    """Regenerate every golden file into ``out_dir``; return the written paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    streams = _streams()
    written: list[Path] = []
    for name in GOLDEN_NAMES:
        path = out_dir / f"{name}.json"
        path.write_text(_dump(render_golden(streams[name])), encoding="utf-8")
        written.append(path)
    sanitize_path = out_dir / "sanitize_cases.json"
    sanitize_path.write_text(_dump(sanitize_cases()), encoding="utf-8")
    written.append(sanitize_path)
    return sorted(written)


REPORT_KINDS: tuple[str, ...] = ("full", "partial", "lookup")
REPORTS_DIR = GOLDENS_DIR / "reports"


def render_report_fixture(kind: str) -> dict[str, Any]:
    """One report fixture: events+display, the ``run.finished`` extras, markdown.

    Deliberately kept out of the top-level goldens directory: the reducer
    golden test only reads those. The TS UI tests feed ``events`` through the
    reducer and ``finished`` into the transcript exactly like the bridge does.
    """
    from finai.bridge.fake_report import fake_events, fake_markdown, fake_material
    from finai.report_view import build_report_view, evidence_availability

    name = f"report_{kind}"
    events = _normalized(fake_events(hdfc_run_events(), kind), name)  # type: ignore[arg-type]
    availability: list[dict[str, Any]] | None = None
    evidence_status: str | None = None
    for event in events:
        if isinstance(event, RunCompleted):
            evidence_status = event.evidence_status
            availability = list(event.evidence_availability)
    view = build_report_view(fake_material(kind))  # type: ignore[arg-type]
    rows = evidence_availability(availability)
    golden = render_golden(events)
    return {
        "events": golden["events"],
        "finished": {
            "outcome": "completed",
            "report": view.model_dump(mode="json") if view is not None else None,
            "evidence_status": evidence_status,
            "evidence_availability": (
                [row.model_dump(mode="json") for row in rows] if rows else None
            ),
        },
        "markdown": fake_markdown(kind),  # type: ignore[arg-type]
    }


def write_report_fixtures(out_dir: Path | str = REPORTS_DIR) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for kind in REPORT_KINDS:
        path = out_dir / f"report-{kind}.json"
        path.write_text(_dump(render_report_fixture(kind)), encoding="utf-8")
        written.append(path)
    return written


def main() -> None:
    for path in [*write_golden(GOLDENS_DIR), *write_report_fixtures(REPORTS_DIR)]:
        print(f"wrote {path.relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    main()
