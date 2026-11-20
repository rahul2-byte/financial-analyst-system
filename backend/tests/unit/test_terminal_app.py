import asyncio
import json
from uuid import uuid4

from app.events.models import (
    ApprovalRequested,
    ClarificationRequested,
    EventFactory,
    RunCompleted,
    RunStarted,
    StageStarted,
    TextDelta,
)
from finai.app import Composer, FinAIApp
from tests.fixtures.hdfc_run import (
    chat_only_events,
    hdfc_run_events,
    partial_run_events,
)
from textual.widgets import Button, Static


def test_textual_app_uses_external_stylesheet() -> None:
    assert FinAIApp.CSS == ""
    assert FinAIApp.CSS_PATH == [
        "styles/tokens.tcss",
        "styles/layout.tcss",
        "styles/components.tcss",
    ]


def test_textual_app_keeps_terminal_copy_shortcut_available() -> None:
    shortcuts = {binding[0]: binding[1] for binding in FinAIApp.BINDINGS}

    assert shortcuts["ctrl+c"] == "cancel_or_exit"
    assert shortcuts["ctrl+shift+c"] == "copy_text"


def test_textual_app_uses_adaptive_workbench_layout() -> None:
    async def scenario() -> None:
        app = FinAIApp()
        async with app.run_test(size=(160, 40)):
            assert app.screen.has_class("layout-wide")
            assert app.query_one("#navigation")
            assert app.query_one("#context-rail")
            assert app.query_one("#nav-sessions")
            assert app.query_one("#send")

        app = FinAIApp()
        async with app.run_test(size=(80, 24)):
            assert app.screen.has_class("layout-narrow")

    asyncio.run(scenario())


async def _stream(_query: str):
    factory = EventFactory(uuid4())
    for event in (
        factory.make(RunStarted, query="INFY"),
        factory.make(TextDelta, text="answer"),
        factory.make(RunCompleted, terminal_status="success"),
    ):
        yield event


def test_textual_app_submits_and_renders_events() -> None:
    async def scenario() -> None:
        app = FinAIApp(_stream)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#composer")
            await pilot.press("i", "n", "f", "y", "enter")
            await pilot.pause(0.1)
            assert app.state.response_text == "answer"
            assert app.state.terminal_status == "success"

    asyncio.run(scenario())


def test_welcome_panel_dismisses_after_first_prompt() -> None:
    async def scenario() -> None:
        app = FinAIApp(_stream)
        async with app.run_test(size=(80, 24)) as pilot:
            assert app.query_one("#welcome", Static).display
            await pilot.click("#composer")
            await pilot.press(*"INFY", "enter")
            await pilot.pause(0.05)
            assert not app.query_one("#welcome", Static).display

    asyncio.run(scenario())


def test_clear_keeps_new_prompt_path_usable() -> None:
    async def scenario() -> None:
        app = FinAIApp(_stream)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#composer")
            await pilot.press("/", "c", "l", "e", "a", "r", "enter")
            await pilot.pause(0.05)
            await pilot.press(*"INFY", "enter")
            await pilot.pause(0.05)
            assert app.state.response_text == "answer"

    asyncio.run(scenario())


def test_each_run_has_an_isolated_response_buffer() -> None:
    async def stream(query: str):
        factory = EventFactory(uuid4())
        yield factory.make(RunStarted, query=query)
        yield factory.make(TextDelta, text=query)
        yield factory.make(RunCompleted, terminal_status="success")

    async def scenario() -> None:
        app = FinAIApp(stream)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#composer")
            await pilot.press(*"first", "enter")
            await pilot.pause(0.1)
            await pilot.press(*"second", "enter")
            await pilot.pause(0.1)
            assert len(list(app.query(".assistant-message"))) == 2
            assert app.state.response_text == "second"
            assert len(list(app.query(".run-activity"))) == 2

    asyncio.run(scenario())


def test_live_run_uses_one_stable_activity_panel_and_streaming_message() -> None:
    async def stream(_query: str):
        factory = EventFactory(uuid4())
        yield factory.make(RunStarted, query="INFY")
        yield factory.make(StageStarted, stage="research", label="Searching filings")
        yield factory.make(TextDelta, text="first ")
        await asyncio.sleep(0.2)
        yield factory.make(TextDelta, text="second")
        yield factory.make(RunCompleted, terminal_status="success")

    async def scenario() -> None:
        app = FinAIApp(stream)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#composer")
            await pilot.press(*"INFY", "enter")
            await pilot.pause(0.05)
            assert len(list(app.query(".run-activity"))) == 1
            assert len(list(app.query(".assistant-message"))) == 1
            await pilot.pause(0.3)
            assert len(list(app.query(".run-activity"))) == 1
            assert app.state.response_text == "first second"

    asyncio.run(scenario())


def test_textual_app_cancels_active_run() -> None:
    async def blocking_stream(_query: str):
        await asyncio.sleep(10)
        yield  # pragma: no cover

    async def scenario() -> None:
        app = FinAIApp(blocking_stream)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#composer")
            await pilot.press("i", "n", "f", "y", "enter")
            await pilot.pause(0.05)
            await pilot.press("ctrl+c")
            await pilot.pause(0.05)
            assert app.state.phase.value == "cancelled"

    asyncio.run(scenario())


def test_textual_app_escape_cancels_active_run() -> None:
    async def blocking_stream(_query: str):
        await asyncio.sleep(10)
        yield  # pragma: no cover

    async def scenario() -> None:
        app = FinAIApp(blocking_stream)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#composer")
            await pilot.press("i", "n", "f", "y", "enter")
            await pilot.pause(0.05)
            await pilot.press("escape")
            await pilot.pause(0.05)
            assert app.state.phase.value == "cancelled"

    asyncio.run(scenario())


def test_textual_app_exits_when_ctrl_c_is_pressed_at_idle() -> None:
    async def scenario() -> None:
        app = FinAIApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("ctrl+c")
            assert app.return_value is not None or app._closed

    asyncio.run(scenario())


def test_textual_app_exits_with_ctrl_z() -> None:
    async def scenario() -> None:
        app = FinAIApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("ctrl+z")
            assert app.return_value is not None or app._closed

    asyncio.run(scenario())


def test_textual_app_requires_explicit_approval_response() -> None:
    calls: list[str] = []

    async def stream(query: str):
        calls.append(query)
        factory = EventFactory(uuid4())
        yield factory.make(RunStarted, query=query)
        yield factory.make(TextDelta, text="Proposed plan")
        yield factory.make(ApprovalRequested, prompt="Approve plan?")

    async def scenario() -> None:
        app = FinAIApp(stream)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#composer")
            await pilot.press(*"analyze INFY", "enter")
            await pilot.pause(0.1)
            assert app.state.phase.value == "waiting_for_approval"
            await pilot.press("n")
            await pilot.pause(0.05)
            assert calls == ["analyze INFY"]
            assert app.state.phase.value == "idle"

    asyncio.run(scenario())


def test_textual_app_refreshes_visible_status_while_run_is_active() -> None:
    async def stream(query: str):
        factory = EventFactory(uuid4())
        yield factory.make(RunStarted, query=query)
        yield factory.make(StageStarted, stage="research", label="Searching filings")
        await asyncio.sleep(1)

    async def scenario() -> None:
        app = FinAIApp(stream)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#composer")
            await pilot.press(*"analyze INFY", "enter")
            await pilot.pause(0.1)
            status = app.query_one("#status", Static).content
            activity = app.query_one(".activity", Static).content
            assert "guided" in str(status)
            assert "F1 help" in str(status)
            assert "Searching filings" in str(activity)

    asyncio.run(scenario())


def test_command_palette_shows_descriptions_for_slash_prefix() -> None:
    async def scenario() -> None:
        app = FinAIApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#composer")
            await pilot.press("/")
            await pilot.pause(0.05)
            menu = app.query_one("#command-menu", Static)
            assert "Commands" in str(menu.content)
            assert "/status" in str(menu.content)
            assert "Show current run status" in str(menu.content)

    asyncio.run(scenario())


def test_trace_command_shows_live_ledger_path_and_recent_events(tmp_path) -> None:
    async def scenario() -> None:
        from finai.session_store import SessionStore

        store = SessionStore(tmp_path / ".finai", "session")
        app = FinAIApp(session_store=store)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#composer")
            await pilot.press("/", "t", "r", "a", "c", "e", "enter")
            await pilot.pause(0.05)
            rendered = "\n".join(str(widget.render()) for widget in app.query("Static"))
            assert "Trace" in rendered
            assert "events.v1.jsonl" in rendered

    asyncio.run(scenario())


def test_reports_button_renders_latest_partial_saved_report(tmp_path) -> None:
    from finai.session_store import SessionStore

    store = SessionStore(tmp_path / ".finai", "session")
    run_path = store.session_dir / "runs" / "run-1.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "session_id": "session",
                "query": "Analyse INFY",
                "status": "partial",
                "created_at": "2026-09-19T10:00:00+00:00",
                "events": [
                    {"type": "response.delta", "text": "Saved report body"},
                    {"type": "run.completed", "terminal_status": "partial"},
                ],
            }
        ),
        encoding="utf-8",
    )

    async def scenario() -> None:
        app = FinAIApp(session_store=store)
        async with app.run_test(size=(80, 24)) as pilot:
            await app.on_button_pressed(Button.Pressed(app.query_one("#nav-reports")))
            await pilot.pause(0.05)
            assert len(list(app.query(".assistant-message"))) == 1

    asyncio.run(scenario())


def test_reports_button_shows_empty_state_without_saved_report(tmp_path) -> None:
    from finai.session_store import SessionStore

    async def scenario() -> None:
        app = FinAIApp(session_store=SessionStore(tmp_path / ".finai", "session"))
        async with app.run_test(size=(80, 24)) as pilot:
            await app.on_button_pressed(Button.Pressed(app.query_one("#nav-reports")))
            await pilot.pause(0.05)
            rendered = "\n".join(str(widget.render()) for widget in app.query("Static"))
            assert "No saved report is available" in rendered

    asyncio.run(scenario())


def test_session_picker_uses_compact_ids() -> None:
    from finai.screens import SessionScreen

    screen = SessionScreen(
        [
            {
                "id": "1234567890abcdef1234567890abcdef",
                "title": "Analyse HDFC Bank",
                "message_count": "4",
                "last_status": "success",
            }
        ]
    )
    assert "12345678" in screen._body()
    assert "1234567890abcdef1234567890abcdef" not in screen._body()


def test_approval_is_a_keyboard_modal() -> None:
    async def stream(_query: str):
        factory = EventFactory(uuid4())
        yield factory.make(RunStarted, query="analyze INFY")
        yield factory.make(ApprovalRequested, prompt="Retrieve filings?")

    async def scenario() -> None:
        app = FinAIApp(stream)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#composer")
            await pilot.press(*"analyze INFY", "enter")
            await pilot.pause(0.1)
            assert app.screen.query_one("#approval-modal")
            await pilot.press("n")
            await pilot.pause(0.05)
            assert app.screen.id == "_default"
            assert app.state.phase.value == "idle"

    asyncio.run(scenario())


def test_approval_does_not_leave_control_text_in_composer() -> None:
    async def stream(_query: str):
        factory = EventFactory(uuid4())
        yield factory.make(RunStarted, query="analyze INFY")
        yield factory.make(ApprovalRequested, prompt="Retrieve filings?")

    async def scenario() -> None:
        app = FinAIApp(stream)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#composer")
            await pilot.press(*"analyze INFY", "enter")
            await pilot.pause(0.05)
            await pilot.press("y")
            await pilot.pause(0.05)
            assert app.query_one("#composer", Composer).text == ""

    asyncio.run(scenario())


def test_approval_resubmits_as_approval_continuation() -> None:
    calls: list[str] = []

    async def stream(query: str):
        calls.append(query)
        factory = EventFactory(uuid4())
        yield factory.make(RunStarted, query=query)
        if len(calls) == 1:
            yield factory.make(ApprovalRequested, prompt="Retrieve filings?")
        else:
            yield factory.make(TextDelta, text="approved")
            yield factory.make(RunCompleted, terminal_status="success")

    async def scenario() -> None:
        app = FinAIApp(stream)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#composer")
            await pilot.press(*"analyze INFY", "enter")
            await pilot.pause(0.05)
            await pilot.press("y")
            await pilot.pause(0.1)
            assert calls == ["analyze INFY", "yes"]

    asyncio.run(scenario())


def _rendered(app: FinAIApp) -> str:
    return "\n".join(str(widget.render()) for widget in app.query("Static"))


def test_context_rail_is_hidden_by_default_and_f2_toggles_it() -> None:
    async def scenario() -> None:
        app = FinAIApp()
        async with app.run_test(size=(160, 40)) as pilot:
            rail = app.query_one("#context-rail")
            assert not rail.display
            await pilot.press("f2")
            assert rail.display
            await pilot.press("f2")
            assert not rail.display

    asyncio.run(scenario())


def test_replayed_hdfc_run_renders_answer_one_sources_block_and_footer() -> None:
    """The real run numbered its report below an already-applied event."""
    events = hdfc_run_events()

    async def stream(_query: str):
        for event in events:
            yield event

    async def scenario() -> None:
        app = FinAIApp(stream)
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.click("#composer")
            await pilot.press(*"HDFCBANK", "enter")
            await pilot.pause(0.5)
            assert len(app.state.response_text) > 400
            messages = list(app.query(".assistant-message"))
            assert len(messages) == 1
            body = messages[0].body.content  # type: ignore[attr-defined]
            assert "Executive summary" in body.markup
            assert len(list(app.query(".sources-message"))) == 1
            assert len(list(app.query(".run-footer"))) == 1
            text = _rendered(app)
            assert "Run artifact" not in text
            assert "✓ complete · 51.4s · 3 sources" in text
            assert "Gathered evidence · 4 tools" in text
            assert "⎿" not in text  # collapsed after completion
            await pilot.press("ctrl+o")
            await pilot.pause(0.1)
            assert "Fetched fundamentals · received 17 fields" in _rendered(app)
            await pilot.press("ctrl+o")
            await pilot.pause(0.1)
            assert "⎿" not in _rendered(app)
            await pilot.press(*"/artifact", "enter")
            await pilot.pause(0.1)
            assert "run.json" in _rendered(app)

    asyncio.run(scenario())


def test_clarification_renders_as_assistant_answer_with_candidates() -> None:
    prompt = (
        "Which company did you mean?\n- HDFC Bank (HDFCBANK)\n- HDFC Life (HDFCLIFE)"
    )

    async def stream(_query: str):
        factory = EventFactory(uuid4())
        yield factory.make(RunStarted, query="hdfc")
        yield factory.make(ClarificationRequested, prompt=prompt)
        yield factory.make(RunCompleted, terminal_status="awaiting_clarification")

    async def scenario() -> None:
        app = FinAIApp(stream)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.click("#composer")
            await pilot.press(*"hdfc", "enter")
            await pilot.pause(0.2)
            messages = list(app.query(".assistant-message"))
            assert len(messages) == 1
            markup = messages[0].body.content.markup  # type: ignore[attr-defined]
            assert "HDFCBANK" in markup and "HDFC Bank" in markup
            assert "HDFCLIFE" in markup and "HDFC Life" in markup
            assert "FIN-AI" not in markup
            assert not list(app.query(".run-footer"))

    asyncio.run(scenario())


def test_chat_only_reply_shows_no_trail_and_no_disclaimer() -> None:
    events = chat_only_events()

    async def stream(_query: str):
        for event in events:
            yield event

    async def scenario() -> None:
        app = FinAIApp(stream)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.click("#composer")
            await pilot.press(*"Hello", "enter")
            await pilot.pause(0.4)
            text = _rendered(app)
            assert "Hello! Ask me" in text or app.state.response_text
            assert "Preparing research" not in text
            assert "Gathered evidence" not in text
            assert "limited to verified data" not in text
            assert all(not w.display for w in app.query(".run-activity"))

    asyncio.run(scenario())


def test_partial_run_names_failure_in_footer_and_never_leaks_raw_ids() -> None:
    events = partial_run_events()

    async def stream(_query: str):
        for event in events:
            yield event

    async def scenario() -> None:
        app = FinAIApp(stream)
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.click("#composer")
            await pilot.press(*"hdfc", "enter")
            await pilot.pause(0.4)
            text = _rendered(app)
            assert "Gathered evidence · 3 tools · news unavailable" in text
            assert "◐ partial · news unavailable · 58.1s · 2 sources" in text
            assert "limited to verified data" not in text
            await pilot.press("ctrl+o")
            await pilot.pause(0.1)
            text = _rendered(app)
            assert "✗ News · no usable articles" in text
            assert "news:" not in text
            header = str(app.query_one("#topbar").render())
            assert header.rstrip().endswith("HDFCBANK.NS")

    asyncio.run(scenario())
