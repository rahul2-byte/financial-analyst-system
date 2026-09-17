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
    render_command,
    render_context,
    render_header,
    render_response,
    render_sources,
    render_user_message,
)
from finai.state import PresentationState, reduce_event
from rich.console import Console


def test_renderers_distinguish_user_and_command_content() -> None:
    user = render_user_message("Analyze INFY")
    assert "You" in user.plain
    assert "Analyze INFY" in user.plain
    assert user._spans
    assert "/status" in render_command("status", []).plain


def test_source_renderer_marks_files_and_links_urls() -> None:
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

    assert "[file] INFY Form 10-K" in rendered.plain
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

    assert render_activity(state).plain.startswith("Response · streaming")


def test_response_renderer_uses_plain_text_while_streaming() -> None:
    state = reduce_event(
        PresentationState(),
        EventFactory(__import__("uuid").uuid4()).make(TextDelta, text="partial"),
    )

    rendered = render_response(state, streaming=True)

    stream = StringIO()
    console = Console(width=80, file=stream)
    console.print(rendered)
    assert "FIN-AI" in stream.getvalue()
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
    rendered = render_header(
        PresentationState(), mode="guided", session_id="1234567890abcdef"
    )

    assert "session 12345678" in rendered.plain
    assert "1234567890abcdef" not in rendered.plain


def test_plain_renderer_labels_partial_completion() -> None:
    event = EventFactory(__import__("uuid").uuid4()).make(
        RunCompleted,
        terminal_status="partial",
    )

    assert "Partial response" in render_event(event)
