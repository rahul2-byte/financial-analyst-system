"""Phase 1 CLI/TUI regressions: one-shot streaming, render coalescing, cancel."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.events.models import (
    ClarificationRequested,
    EventFactory,
    RunCancelled,
    RunCompleted,
    RunFailed,
    RunStarted,
    TextDelta,
    ToolCompleted,
    ToolStarted,
)
from finai import cli
from finai.app import FinAIApp
from finai.widgets import Composer
from textual.widgets import Static


def _repl(events: list, closed: list | None = None) -> SimpleNamespace:
    async def typed_stream(_q: str):
        for event in events:
            yield event

    async def aclose() -> None:
        if closed is not None:
            closed.append(True)

    return SimpleNamespace(
        typed_stream=typed_stream,
        session_id="sess1",
        hive_service=SimpleNamespace(aclose=aclose),
    )


def _run(events: list, *, as_json: bool = False) -> int:
    return asyncio.run(cli.run_one_shot(_repl(events), "q", as_json=as_json))  # type: ignore[arg-type]


def _events(*tail: tuple) -> list:
    factory = EventFactory(uuid4())
    out = [
        factory.make(RunStarted, query="q"),
        factory.make(ToolStarted, tool="quote"),
        factory.make(ToolCompleted, tool="quote"),
        factory.make(TextDelta, text="hello "),
        factory.make(TextDelta, text="world"),
    ]
    out.extend(factory.make(kind, **fields) for kind, fields in tail)
    return out


@pytest.mark.parametrize(
    ("tail", "code"),
    [
        ((RunCompleted, {"terminal_status": "success"}), 0),
        ((RunFailed, {"message": "boom"}), 1),
        ((RunCancelled, {}), 1),
        ((RunCompleted, {"terminal_status": "denied"}), 1),
        ((ClarificationRequested, {"prompt": "Which?"}), 2),
        ((RunCompleted, {"terminal_status": "awaiting_clarification"}), 2),
        ((RunCompleted, {"terminal_status": "partial"}), 3),
        ((RunCompleted, {"terminal_status": "completed_with_limited_evidence"}), 3),
        (
            (
                RunCompleted,
                {"terminal_status": "success", "evidence_status": "limited"},
            ),
            3,
        ),
        (
            (
                RunCompleted,
                {"terminal_status": "success", "evidence_status": "complete"},
            ),
            0,
        ),
    ],
)
def test_one_shot_exit_codes(tail: tuple, code: int) -> None:
    assert _run(_events(tail)) == code
    assert _run(_events(tail), as_json=True) == code


def test_one_shot_closes_hive_client_on_error() -> None:
    closed: list[bool] = []

    async def boom(_q: str):
        raise RuntimeError("x")
        yield

    repl = _repl([], closed)
    repl.typed_stream = boom
    with pytest.raises(RuntimeError):
        asyncio.run(cli.run_one_shot(repl, "q", as_json=False))  # type: ignore[arg-type]
    assert closed == [True]


def test_progress_goes_to_stderr_text_to_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _run(_events((RunCompleted, {"terminal_status": "success"})))
    captured = capsys.readouterr()
    assert "hello world" in captured.out
    assert "quote" not in captured.out
    assert "Completed" not in captured.out
    assert "quote" in captured.err
    assert "Completed" in captured.err


def test_json_mode_emits_ordered_jsonl(capsys: pytest.CaptureFixture[str]) -> None:
    events = _events((RunCompleted, {"terminal_status": "success"}))
    _run(events, as_json=True)
    lines = capsys.readouterr().out.splitlines()
    parsed = [json.loads(line) for line in lines]
    assert [p["type"] for p in parsed] == [e.type for e in events]
    sequences = [p["meta"]["sequence"] for p in parsed]
    assert sequences == sorted(sequences)


def test_help_documents_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.parse_arguments(["--help"])
    out = capsys.readouterr().out
    assert "exit codes" in out
    assert "130" in out


def _text(app: FinAIApp) -> str:
    parts = []
    for widget in app.query("#conversation Static"):
        rendered = widget.render()
        parts.append(str(getattr(rendered, "plain", rendered)))
    return "\n".join(parts)


def test_markdown_updates_are_coalesced() -> None:
    deltas = 200

    async def stream(_q: str):
        factory = EventFactory(uuid4())
        yield factory.make(RunStarted, query="q")
        for i in range(deltas):
            yield factory.make(TextDelta, text=f"w{i} ")
        yield factory.make(RunCompleted, terminal_status="success")

    async def scenario() -> None:
        app = FinAIApp(stream)
        async with app.run_test(size=(100, 30)) as pilot:
            app.query_one("#composer", Composer).text = "hi"
            await pilot.press("enter")
            await pilot.pause(0.6)
            assert app.state.response_text == "".join(f"w{i} " for i in range(deltas))
            assert app.response_render_count < deltas // 4
            assert app._delta_dirty is False

    asyncio.run(scenario())


def test_cancel_with_queued_query_shows_cancelled_and_starts_next() -> None:
    started: list[str] = []
    release = asyncio.Event()

    async def stream(query: str):
        started.append(query)
        factory = EventFactory(uuid4())
        yield factory.make(RunStarted, query=query)
        if query == "first":
            await release.wait()  # never released; cancelled
        yield factory.make(TextDelta, text=f"answer {query}")
        yield factory.make(RunCompleted, terminal_status="success")

    async def scenario() -> None:
        app = FinAIApp(stream)
        async with app.run_test(size=(100, 30)) as pilot:
            composer = app.query_one("#composer", Composer)
            composer.text = "first"
            await pilot.press("enter")
            await pilot.pause(0.1)
            composer.text = "second"
            await pilot.press("enter")
            await pilot.pause(0.1)
            assert started == ["first"]
            app.action_cancel_run()
            await pilot.pause(0.5)
            assert started == ["first", "second"]
            assert "Cancelled" in _text(app)
            first_activity = next(iter(app.query(".run-activity")))
            assert first_activity.display is False
            assert "answer second" in app.state.response_text
            assert app._run_task is None or app._run_task.done()

    asyncio.run(scenario())


def test_cancel_without_queue_leaves_cancelled_row() -> None:
    async def stream(query: str):
        factory = EventFactory(uuid4())
        yield factory.make(RunStarted, query=query)
        await asyncio.sleep(30)
        yield factory.make(RunCompleted, terminal_status="success")

    async def scenario() -> None:
        app = FinAIApp(stream)
        async with app.run_test(size=(100, 30)) as pilot:
            app.query_one("#composer", Composer).text = "q"
            await pilot.press("enter")
            await pilot.pause(0.1)
            app.action_cancel_run()
            await pilot.pause(0.3)
            assert "Cancelled" in _text(app)
            assert isinstance(app.query_one("#status", Static), Static)

    asyncio.run(scenario())
