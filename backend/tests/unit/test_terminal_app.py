import asyncio
from uuid import uuid4

from app.events.models import (
    ApprovalRequested,
    EventFactory,
    RunCompleted,
    RunStarted,
    StageStarted,
    TextDelta,
)
from finai.app import Composer, FinAIApp
from textual.widgets import Static


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
            assert "researching" in str(status)
            assert "processing" in str(activity)

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


def test_session_picker_uses_compact_ids() -> None:
    from finai.screens import SessionScreen

    screen = SessionScreen([{
        "id": "1234567890abcdef1234567890abcdef",
        "title": "Analyse HDFC Bank",
        "message_count": "4",
        "last_status": "success",
    }])
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
