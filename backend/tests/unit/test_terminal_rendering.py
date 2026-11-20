from io import StringIO

from app.events.models import (
    EventFactory,
    RunCompleted,
    SourcesUpdated,
    StageStarted,
    TextDelta,
)
from finai.plain import render_event
from finai.render import (
    render_activity,
    render_clarification,
    render_command,
    render_context,
    render_footer,
    render_header,
    render_hints,
    render_response,
    render_saved_report,
    render_sources,
    render_user_message,
)
from finai.state import PresentationPhase, PresentationState, reduce_event
from rich.console import Console


def test_renderers_distinguish_user_and_command_content() -> None:
    user = render_user_message("Analyze INFY")
    assert user.plain.startswith("› ")
    assert "You" not in user.plain
    assert "Analyze INFY" in user.plain
    assert user._spans
    assert "/status" in render_command("status", []).plain


def test_source_renderer_marks_links_urls() -> None:
    factory = EventFactory(__import__("uuid").uuid4())
    state = reduce_event(
        PresentationState(),
        factory.make(
            SourcesUpdated,
            sources=[
                {
                    "title": "INFY Form 10-K",
                    "source_type": "filing",
                    "url": "https://sec.gov/filing/1",
                }
            ],
        ),
    )

    rendered = render_sources(state.sources)

    assert "[1] INFY Form 10-K" in rendered.plain
    assert "sec.gov" in rendered.plain
    assert any(
        getattr(span.style, "link", None) == "https://sec.gov/filing/1"
        for span in rendered._spans
    )


def test_activity_renderer_labels_streaming_as_response() -> None:
    factory = EventFactory(__import__("uuid").uuid4())
    state = PresentationState()
    state = reduce_event(
        state, factory.make(StageStarted, stage="checking", label="Checking request")
    )
    state = reduce_event(state, factory.make(TextDelta, text="Hello"))

    plain = render_activity(state).plain
    assert plain.splitlines()[0].endswith("Checking request")
    assert "  ⎿ Checking request" in plain


def test_response_renderer_uses_plain_text_while_streaming() -> None:
    state = reduce_event(
        PresentationState(),
        EventFactory(__import__("uuid").uuid4()).make(TextDelta, text="partial"),
    )

    rendered = render_response(state)

    stream = StringIO()
    console = Console(width=80, file=stream)
    console.print(rendered)
    assert "FIN-AI" not in stream.getvalue()
    assert "partial" in stream.getvalue()


def test_response_renderer_formats_markdown_table() -> None:
    state = PresentationState(
        response_text="| Company | Revenue |\n| --- | ---: |\n| INFY | 12.4% |"
    )

    stream = StringIO()
    console = Console(width=80, file=stream)
    console.print(render_response(state))

    output = stream.getvalue()
    assert "Company" in output
    assert "Revenue" in output
    assert "12.4%" in output


def test_footer_names_partial_terminal_status_and_counts_sources() -> None:
    state = PresentationState(terminal_status="partial")
    state = reduce_event(
        state,
        EventFactory(__import__("uuid").uuid4()).make(
            RunCompleted, terminal_status="partial"
        ),
    )

    state.sources.append({"name": "upstox", "url": "https://api.upstox.com"})
    footer = render_footer(state, elapsed_s=51.44).plain
    assert footer == "◐ partial · 51.4s · 1 source"


def test_footer_marks_failure_in_loss_colour() -> None:
    state = PresentationState(terminal_status="failed")
    state.phase = PresentationPhase.FAILED
    footer = render_footer(state, elapsed_s=2.0)
    assert footer.plain == "✗ failed · 2.0s"
    assert "#D9796B" in str(footer.style)


def test_hints_line_has_mode_model_session_and_help() -> None:
    plain = render_hints(
        mode="guided", model="claude-haiku-5.5", session_id="1234567890", width=100
    ).plain
    assert plain.startswith("guided · claude-haiku-5.5 · session 12345678")
    assert plain.endswith("/ commands · F1 help")
    assert len(plain) == 100


def test_saved_report_renderer_preserves_partial_metadata_and_body() -> None:
    rendered = render_saved_report(
        {
            "status": "partial",
            "query": "Analyse INFY",
            "created_at": "2026-09-19T10:00:00+00:00",
            "artifact_path": "/tmp/run-1.json",
            "report_text": "Saved report body",
        }
    )

    assert "Partial evidence" in rendered.markup
    assert "Saved report body" in rendered.markup
    assert "run-1.json" in rendered.markup


def test_context_renderer_shows_only_known_runtime_state() -> None:
    state = PresentationState(
        query="Analyze INFY for one year",
        sources=[{"title": "Annual report", "source_type": "filing"}],
    )

    rendered = render_context(state, mode="guided", session_id="local-session")

    assert "Analyze INFY for one year" in rendered.plain
    assert "1 verified source" in rendered.plain
    assert "guided" in rendered.plain
    assert "Ticker" not in rendered.plain


def test_header_compacts_session_identity_for_terminal_chrome() -> None:
    rendered = render_header(PresentationState(), instrument="HDFCBANK.NS")

    assert rendered.plain.startswith("FIN-AI")
    assert rendered.plain.endswith("HDFCBANK.NS")
    assert "guided" not in rendered.plain
    assert render_header(PresentationState()).plain.startswith("FIN-AI")


def test_plain_renderer_labels_partial_completion() -> None:
    event = EventFactory(__import__("uuid").uuid4()).make(
        RunCompleted,
        terminal_status="partial",
    )

    assert "Partial response" in render_event(event)


def test_clarification_aligns_symbols_and_title_cases_names() -> None:
    rendered = render_clarification(
        "Several NSE/BSE instruments match HDFC. Reply with the exact symbol:\n"
        "- HDFCBANK (NSE) HDFC BANK LTD\n"
        "- HDFCAMC (NSE) HDFC ASSET MANAGEMENT COMPANY LTD"
    ).plain
    assert "  HDFCBANK  HDFC Bank Ltd                     · NSE" in rendered
    assert "  HDFCAMC   HDFC Asset Management Company Ltd · NSE" in rendered


def test_tool_labels_are_past_tense_and_failures_hide_raw_ids() -> None:
    from finai.state import ActivityState

    state = PresentationState(
        phase=PresentationPhase.COMPLETE,
        activities={
            "tool:a": ActivityState("data:fetch_stock_data", "completed"),
            "tool:b": ActivityState(
                "news:fetch_news",
                "failed",
                "No usable evidence returned for news:fetch_news",
            ),
        },
    )
    expanded = render_activity(state, expanded=True).plain
    assert "Fetched stock data" in expanded
    assert "✗ News · no usable articles" in expanded
    assert "news:" not in expanded
    assert "⎿" not in render_activity(state).plain
    assert (
        render_activity(PresentationState(phase=PresentationPhase.COMPLETE)).plain == ""
    )
