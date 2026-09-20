import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from app.events.models import EventFactory, RunCompleted, RunStarted, TextDelta
from app.models.request_models import Message
from finai.__main__ import FinAIRepl
from finai.session_store import SessionStore


def _write_saved_run(
    root,
    session_id: str,
    run_id: str,
    *,
    created_at: str,
    status: str,
    text: str = "report",
) -> None:
    path = root / "sessions" / session_id / "runs" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "session_id": session_id,
                "query": "Analyse INFY",
                "status": status,
                "created_at": created_at,
                "events": [
                    {"type": "response.delta", "text": text},
                    {"type": "run.completed", "terminal_status": status},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_latest_saved_report_selects_newest_eligible_run(tmp_path) -> None:
    root = tmp_path / ".finai"
    now = datetime.now(UTC)
    _write_saved_run(
        root,
        "old-session",
        "old-run",
        created_at=(now - timedelta(minutes=1)).isoformat(),
        status="success",
        text="old report",
    )
    _write_saved_run(
        root,
        "new-session",
        "new-run",
        created_at=now.isoformat(),
        status="partial",
        text="new report",
    )

    report = SessionStore.latest_saved_report(root)

    assert report is not None
    assert report["run_id"] == "new-run"
    assert report["status"] == "partial"
    assert report["report_text"] == "new report"


def test_latest_saved_report_ignores_failed_and_reportless_runs(tmp_path) -> None:
    root = tmp_path / ".finai"
    now = datetime.now(UTC)
    _write_saved_run(
        root,
        "session",
        "failed-run",
        created_at=now.isoformat(),
        status="failed",
    )
    path = root / "sessions" / "session" / "runs" / "empty-run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "run_id": "empty-run",
                "session_id": "session",
                "status": "partial",
                "created_at": (now - timedelta(minutes=1)).isoformat(),
                "events": [{"type": "run.completed", "terminal_status": "partial"}],
            }
        ),
        encoding="utf-8",
    )

    assert SessionStore.latest_saved_report(root) is None


def test_latest_saved_report_ignores_structurally_invalid_json_artifact(
    tmp_path,
) -> None:
    root = tmp_path / ".finai"
    path = root / "sessions" / "session" / "runs" / "invalid.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]", encoding="utf-8")

    assert SessionStore.latest_saved_report(root) is None


def test_session_store_persists_history_and_run_artifacts(tmp_path) -> None:
    store = SessionStore(tmp_path / ".finai", "session-1")
    store.append_message(Message(role="user", content="Analyze INFY"))
    store.append_message(Message(role="assistant", content="Working."))
    run_path = store.write_run(
        query="Analyze INFY",
        events=[{"type": "run.completed"}],
        run_id="run-1",
        status="completed",
    )

    assert store.load_history() == [
        Message(role="user", content="Analyze INFY"),
        Message(role="assistant", content="Working."),
    ]
    assert json.loads(run_path.read_text())["status"] == "completed"


def test_session_store_round_trips_context_and_pending_interaction(tmp_path) -> None:
    store = SessionStore(tmp_path / ".finai", "session-1")

    store.write_context({"summary": "HDFC Bank analysis", "pinned_facts": ["fact-1"]})
    store.write_pending({"interaction_id": "i-1", "question": "Which period?"})

    assert store.read_context()["summary"] == "HDFC Bank analysis"
    pending = store.read_pending()
    assert pending is not None
    assert pending["interaction_id"] == "i-1"


def test_session_store_rejects_path_traversal_session_ids(tmp_path) -> None:
    with pytest.raises(ValueError, match="session id"):
        SessionStore(tmp_path / ".finai", "../other")


def test_session_listing_includes_activity_metadata(tmp_path) -> None:
    root = tmp_path / ".finai"
    store = SessionStore(root, "session-a")
    store.append_message(Message(role="user", content="Analyze AAPL"))
    store.write_run(query="Analyze AAPL", events=[], run_id="run-1", status="success")

    sessions = SessionStore.list_sessions(root)

    assert sessions[0]["title"] == "Analyze AAPL"
    assert sessions[0]["message_count"] == "1"
    assert sessions[0]["run_count"] == "1"
    assert sessions[0]["last_status"] == "success"


def test_repl_persists_typed_stream_transcript_and_run(tmp_path) -> None:
    repl = FinAIRepl(root=tmp_path / ".finai")

    async def stream(history, query, conversation_id, **kwargs):
        del history, query, kwargs
        factory = EventFactory(conversation_id)
        yield factory.make(RunStarted, query="hello")
        yield factory.make(TextDelta, text="answer")
        yield factory.make(RunCompleted, terminal_status="success", duration_ms=1.0)

    repl.runtime.stream = stream

    async def scenario() -> None:
        events = [event async for event in repl.typed_stream("hello")]
        assert events[-1].type == "run.completed"

    asyncio.run(scenario())
    assert [message.role for message in repl.store.load_history()] == [
        "user",
        "assistant",
    ]
    run_files = list((repl.store.session_dir / "runs").glob("*.json"))
    assert len(run_files) == 1
    assert json.loads(run_files[0].read_text())["status"] == "success"
    trace_records = repl.store.trace.read()
    assert [record["event_type"] for record in trace_records] == [
        "run.started",
        "response.delta",
        "run.completed",
    ]


def test_repl_does_not_duplicate_runtime_persisted_final_report(tmp_path) -> None:
    repl = FinAIRepl(root=tmp_path / ".finai")

    async def stream(history, query, conversation_id, *, message_writer, **kwargs):
        del history, query, kwargs
        message_writer(Message(role="assistant", content="final report"))
        factory = EventFactory(conversation_id)
        yield factory.make(RunStarted, query="Analyse INFY")
        yield factory.make(TextDelta, text="final report")
        yield factory.make(RunCompleted, terminal_status="success", duration_ms=1.0)

    repl.runtime.stream = stream

    async def scenario() -> None:
        _ = [event async for event in repl.typed_stream("Analyse INFY")]

    asyncio.run(scenario())
    assistants = [
        message.content
        for message in repl.store.load_history()
        if message.role == "assistant"
    ]
    assert assistants == ["final report"]


def test_store_marks_abandoned_run_interrupted(tmp_path) -> None:
    store = SessionStore(tmp_path / ".finai", "session")
    run = store.session_dir / "runs" / "run.json"
    run.parent.mkdir(parents=True)
    run.write_text(
        json.dumps({"run_id": "run", "status": "running"}) + "\n",
        encoding="utf-8",
    )

    assert store.mark_incomplete_runs_interrupted() == 1
    assert json.loads(run.read_text(encoding="utf-8"))["status"] == "interrupted"
    assert store.trace.read()[-1]["event_type"] == "run.interrupted"
    assert store.mark_incomplete_runs_interrupted() == 0


def test_begin_run_is_recoverable_before_completion(tmp_path) -> None:
    store = SessionStore(tmp_path / ".finai", "session")

    path = store.begin_run(query="Analyze INFY", run_id="run-1")
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "running"

    assert store.mark_incomplete_runs_interrupted() == 1
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "interrupted"
