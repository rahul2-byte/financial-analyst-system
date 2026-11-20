"""Phase 0 UX regressions for the FIN-AI terminal."""

import asyncio
import contextlib
import io
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.events.models import (
    ClarificationRequested,
    EventFactory,
    RunCompleted,
    RunStarted,
    SourcesUpdated,
    TextDelta,
)
from app.models.request_models import Message
from finai import cli
from finai.app import Composer, FinAIApp
from finai.plain import render_plain
from finai.render import render_header
from finai.screens import HelpScreen, SessionScreen
from finai.session_store import SessionStore
from finai.state import PresentationState
from textual.widgets import Button, Static


def _plain(widget: Static) -> str:
    rendered = widget.render()
    return str(getattr(rendered, "plain", rendered))


def _text(app: FinAIApp) -> str:
    return "\n".join(_plain(w) for w in app.query("#conversation Static"))


def _seed(root: Path, sid: str, *queries: str) -> SessionStore:
    store = SessionStore(root, sid)
    for query in queries:
        store.append_message(Message(role="user", content=query))
        store.append_message(Message(role="assistant", content=f"answer to {query}"))
    return store


async def _submit(app: FinAIApp, pilot, text: str) -> None:
    app.query_one("#composer", Composer).text = text
    await pilot.press("enter")
    await pilot.pause(0.1)


async def _stream(query: str):
    factory = EventFactory(uuid4())
    yield factory.make(RunStarted, query=query)
    yield factory.make(TextDelta, text="ok")
    yield factory.make(RunCompleted, terminal_status="success")


# F-01
def test_history_lists_prior_queries(tmp_path: Path) -> None:
    store = _seed(tmp_path, "s1", "first question", "second question")

    async def scenario() -> None:
        app = FinAIApp(session_store=store)
        async with app.run_test(size=(100, 30)) as pilot:
            await _submit(app, pilot, "/history")
            text = _text(app)
            assert "1. first question" in text
            assert "2. second question" in text

    asyncio.run(scenario())


def test_retry_reruns_last_query(tmp_path: Path) -> None:
    store = _seed(tmp_path, "s1", "first question", "second question")
    seen: list[str] = []

    async def stream(query: str):
        seen.append(query)
        async for event in _stream(query):
            yield event

    async def scenario() -> None:
        app = FinAIApp(stream, session_store=store)
        async with app.run_test(size=(100, 30)) as pilot:
            await _submit(app, pilot, "/retry")
            await pilot.pause(0.2)
            assert seen == ["second question"]

    asyncio.run(scenario())


def test_context_and_compact_report_real_state(tmp_path: Path) -> None:
    store = _seed(tmp_path, "s1", "hello")

    async def scenario() -> None:
        app = FinAIApp(
            session_store=store,
            compact_callback=lambda: {"estimated_tokens": 5, "compacted_messages": 0},
        )
        async with app.run_test(size=(100, 30)) as pilot:
            await _submit(app, pilot, "/context")
            assert "tokens" in _text(app)
            assert "messages     2" in _text(app)
            await _submit(app, pilot, "/compact")
            assert "Nothing to compact" in _text(app)

    asyncio.run(scenario())


def test_unknown_command_reports_error() -> None:
    async def scenario() -> None:
        app = FinAIApp()
        async with app.run_test(size=(100, 30)) as pilot:
            await _submit(app, pilot, "/bogus")
            assert "Unknown command /bogus — try /help" in _text(app)

    asyncio.run(scenario())


# F-02
def test_ctrl_k_opens_picker_and_selection_resumes(tmp_path: Path) -> None:
    store = _seed(tmp_path, "aaa111", "old question")
    resumed: list[str] = []

    def resume(session_id: str) -> None:
        resumed.append(session_id)
        app.session_store = SessionStore(tmp_path, session_id)

    app = FinAIApp(session_store=store, session_callback=resume)

    async def scenario() -> None:
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("ctrl+k")
            await pilot.pause(0.1)
            assert isinstance(app.screen, SessionScreen)
            await pilot.press("enter")
            await pilot.pause(0.2)
            assert resumed == ["aaa111"]
            assert "old question" in _text(app)

    asyncio.run(scenario())


def test_resume_by_prefix(tmp_path: Path) -> None:
    store = _seed(tmp_path, "abc123", "q1")
    _seed(tmp_path, "def456", "other question")
    resumed: list[str] = []

    def resume(session_id: str) -> None:
        resumed.append(session_id)
        app.session_store = SessionStore(tmp_path, session_id)

    app = FinAIApp(session_store=store, session_callback=resume)

    async def scenario() -> None:
        async with app.run_test(size=(100, 30)) as pilot:
            await _submit(app, pilot, "/resume def")
            assert resumed == ["def456"]
            await _submit(app, pilot, "/resume zzz")
            assert "No session matches" in _text(app)

    asyncio.run(scenario())


# F-08
def test_mode_validates_and_sets_mode() -> None:
    async def scenario() -> None:
        app = FinAIApp()
        async with app.run_test(size=(100, 30)) as pilot:
            await _submit(app, pilot, "/mode review")
            assert app.mode == "review"
            assert "review" in _plain(app.query_one("#topbar", Static))
            await _submit(app, pilot, "/mode bogus")
            assert app.mode == "review"
            assert "guided, review, autonomous" in _text(app)

    asyncio.run(scenario())


# F-09
def test_clear_pending_binds_to_current_store(tmp_path: Path) -> None:
    repl = SimpleNamespace(
        store=SessionStore(tmp_path, "a1"), mode="guided", compact_context=dict
    )

    def resume(session_id: str) -> None:
        repl.store = SessionStore(tmp_path, session_id)

    repl.resume_session = resume  # type: ignore[attr-defined]
    app = cli.build_app(repl)  # type: ignore[arg-type]
    repl.resume_session("b2")
    repl.store.write_pending({"kind": "approval"})
    assert app.clear_pending_callback is not None
    app.clear_pending_callback()
    assert repl.store.read_pending() is None


# F-12
def _events(*items):
    factory = EventFactory(uuid4())
    return [factory.make(cls, **kw) for cls, kw in items]


def test_plain_lists_numbered_sources() -> None:
    sources = [
        {
            "title": "Annual Report",
            "source": "HDFC Bank",
            "url": "https://example.com/ar.pdf",
        }
    ]
    out = render_plain(_events((SourcesUpdated, {"sources": sources})))
    assert "[1] Annual Report — HDFC Bank" in out
    assert "https://example.com/ar.pdf" in out


def test_one_shot_clarification_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    async def typed_stream(_q: str):
        for event in _events((ClarificationRequested, {"prompt": "Which company?"})):
            yield event

    async def aclose() -> None:
        return None

    repl = SimpleNamespace(
        typed_stream=typed_stream,
        session_id="sess123",
        llm_service=SimpleNamespace(aclose=aclose),
    )
    code = asyncio.run(cli.run_one_shot(repl, "q", as_json=False))  # type: ignore[arg-type]
    out = capsys.readouterr().out
    assert code == 2
    assert "Which company?" in out
    assert "sess123" in out


# F-13
@pytest.mark.parametrize("width", [40, 60, 80, 120])
def test_header_is_single_line(width: int) -> None:
    text = render_header(
        PresentationState(), mode="guided", session_id="1234567890", width=width
    )
    assert "\n" not in text.plain
    assert len(text.plain) <= width


# F-14
def test_help_modal_and_question_mark_types_in_composer() -> None:
    async def scenario() -> None:
        app = FinAIApp()
        async with app.run_test(size=(100, 30)) as pilot:
            assert not list(app.query("#composer-tools"))
            await pilot.press("question_mark")
            assert app.query_one("#composer", Composer).text == "?"
            assert not isinstance(app.screen, HelpScreen)
            await pilot.press("f1")
            await pilot.pause(0.1)
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape")
            await pilot.pause(0.1)
            assert not isinstance(app.screen, HelpScreen)

    asyncio.run(scenario())


# F-15
def test_sidebar_uses_real_sessions(tmp_path: Path) -> None:
    store = _seed(tmp_path, "s1", "Real stored question")

    async def scenario() -> None:
        app = FinAIApp(session_store=store)
        async with app.run_test(size=(160, 40)):
            text = _plain(app.query_one("#recent-sessions", Static))
            assert "Real stored question" in text
            assert "HDFC Bank Analysis" not in text
            assert not list(app.query("#nav-watchlist"))
            assert not list(app.query("#nav-settings"))
            assert list(app.query(Button))

    asyncio.run(scenario())


# F-10 (cli part)
def test_tracing_init_noise_goes_to_stderr() -> None:
    out, err = io.StringIO(), io.StringIO()

    def noisy() -> None:
        print("Phoenix banner")

    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        cli.quiet_stdout(noisy)
    assert out.getvalue() == ""
    assert "Phoenix banner" in err.getvalue()
