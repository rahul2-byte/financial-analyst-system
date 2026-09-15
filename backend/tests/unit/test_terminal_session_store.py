import asyncio
import json

from app.models.request_models import Message
from app.models.response_models import StreamEvent
from finai.__main__ import FinAIRepl
from finai.session_store import SessionStore


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
    assert json.loads(run_path.read_text())['status'] == "completed"


def test_session_store_round_trips_context_and_pending_interaction(tmp_path) -> None:
    store = SessionStore(tmp_path / ".finai", "session-1")

    store.write_context({"summary": "HDFC Bank analysis", "pinned_facts": ["fact-1"]})
    store.write_pending({"interaction_id": "i-1", "question": "Which period?"})

    assert store.read_context()["summary"] == "HDFC Bank analysis"
    pending = store.read_pending()
    assert pending is not None
    assert pending["interaction_id"] == "i-1"


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
    calls: list[dict[str, object]] = []

    class StreamOrchestrator:
        async def execute_query(self, _query, **kwargs):
            calls.append(kwargs)
            yield StreamEvent(type="status", message="Checking request...")
            yield StreamEvent(type="text_delta", content="answer")
            yield StreamEvent(type="done")

    repl = FinAIRepl(root=tmp_path / ".finai")
    repl.orchestrator = StreamOrchestrator()

    async def scenario() -> None:
        events = [event async for event in repl.typed_stream("hello")]
        assert events[-1].type == "run.completed"

    asyncio.run(scenario())
    assert [message.role for message in repl.store.load_history()] == ["user", "assistant"]
    run_files = list((repl.store.session_dir / "runs").glob("*.json"))
    assert len(run_files) == 1
    assert json.loads(run_files[0].read_text())["status"] == "success"
    assert calls[0]["expose_model_stream"] is True
    trace_records = repl.store.trace.read()
    assert [record["event_type"] for record in trace_records] == [
        "run.started",
        "stage.started",
        "response.delta",
        "run.completed",
    ]


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
