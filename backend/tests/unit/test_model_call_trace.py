import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from app.config import settings
from app.core.model_call_trace import (
    ModelCallTrace,
    capture_stream,
    read_trace,
    safe_endpoint,
)


def test_trace_writes_exact_payload_as_durable_jsonl(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FINAI_MODEL_TRACE", "full")
    monkeypatch.setenv("FINAI_MODEL_TRACE_DIR", str(tmp_path))
    trace = ModelCallTrace.create(
        provider="test-provider",
        model="test-model",
        run_id="run-1",
        conversation_id="conversation-1",
    )

    trace.write("request.started", {"body": {"messages": [{"content": "raw"}]}})
    trace.write("response.completed", {"text": "full answer"})

    records = [json.loads(line) for line in trace.path.read_text().splitlines()]
    assert [record["event"] for record in records] == [
        "request.started",
        "response.completed",
    ]
    assert records[0]["payload"]["body"]["messages"][0]["content"] == "raw"
    assert records[1]["run_id"] == "run-1"
    assert records[1]["conversation_id"] == "conversation-1"
    assert os.stat(trace.path).st_mode & 0o777 == 0o600


def test_trace_is_disabled_without_explicit_opt_in(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("FINAI_MODEL_TRACE", raising=False)
    monkeypatch.setenv("FINAI_MODEL_TRACE_DIR", str(tmp_path))

    assert (
        ModelCallTrace.create(
            provider="test-provider", model="test-model", run_id="run-1"
        )
        is None
    )
    assert not list(Path(tmp_path).glob("**/*.jsonl"))


def test_trace_reads_settings_loaded_from_dotenv(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("FINAI_MODEL_TRACE", raising=False)
    monkeypatch.delenv("FINAI_MODEL_TRACE_DIR", raising=False)
    monkeypatch.setattr(settings, "FINAI_MODEL_TRACE", "full")
    monkeypatch.setattr(settings, "FINAI_MODEL_TRACE_DIR", str(tmp_path))

    trace = ModelCallTrace.create(provider="hive", model="m", run_id="run-1")

    assert trace is not None
    assert trace.path.parent.parent == tmp_path


def test_trace_prunes_files_older_than_seven_days(tmp_path, monkeypatch) -> None:
    import time

    monkeypatch.setenv("FINAI_MODEL_TRACE", "full")
    monkeypatch.setenv("FINAI_MODEL_TRACE_DIR", str(tmp_path))
    stale_dir = Path(tmp_path) / "2026-09-01"
    stale_dir.mkdir()
    stale = stale_dir / "stale.jsonl"
    stale.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "event": "call.started",
                "call_id": "old-call",
                "provider": "hive",
                "model": "test-model",
                "payload": {},
            }
        )
        + "\n"
    )
    (stale_dir / ".finai-model-call-traces").touch(mode=0o600)
    old = time.time() - 8 * 24 * 60 * 60
    os.utime(stale, (old, old))
    os.utime(stale_dir, (old, old))

    trace = ModelCallTrace.create(
        provider="test-provider", model="test-model", run_id="run-1"
    )

    assert trace is not None
    assert not stale.exists()
    assert not stale_dir.exists()


def test_trace_pruning_preserves_unowned_stale_directories(tmp_path, monkeypatch) -> None:
    import time

    monkeypatch.setenv("FINAI_MODEL_TRACE", "full")
    monkeypatch.setenv("FINAI_MODEL_TRACE_DIR", str(tmp_path))
    shared_dir = Path(tmp_path) / "2026-09-01"
    shared_dir.mkdir()
    unrelated = shared_dir / "keep.txt"
    unrelated.write_text("unrelated user data")
    old = time.time() - 8 * 24 * 60 * 60
    os.utime(unrelated, (old, old))
    os.utime(shared_dir, (old, old))

    trace = ModelCallTrace.create(
        provider="test-provider", model="test-model", run_id="run-1"
    )

    assert trace is not None
    assert unrelated.read_text() == "unrelated user data"


def test_trace_does_not_change_permissions_on_existing_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FINAI_MODEL_TRACE", "full")
    monkeypatch.setenv("FINAI_MODEL_TRACE_DIR", str(tmp_path))
    tmp_path.chmod(0o755)

    trace = ModelCallTrace.create(
        provider="test-provider", model="test-model", run_id="run-1"
    )

    assert trace is not None
    assert os.stat(tmp_path).st_mode & 0o777 == 0o755


def test_trace_reader_keeps_records_before_a_torn_final_line(tmp_path) -> None:
    path = tmp_path / "calls.jsonl"
    path.write_text('{"event":"request.started"}\n{"event":')

    assert read_trace(path) == [{"event": "request.started"}]


def test_trace_reader_ignores_torn_utf8_bytes_at_end(tmp_path) -> None:
    path = tmp_path / "calls.jsonl"
    path.write_bytes(b'{"event":"request.started"}\n{"text":"\xff')

    assert read_trace(path) == [{"event": "request.started"}]


def test_calls_in_same_run_share_one_trace_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FINAI_MODEL_TRACE", "full")
    monkeypatch.setenv("FINAI_MODEL_TRACE_DIR", str(tmp_path))
    first = ModelCallTrace.create(provider="hive", model="m", run_id="run-1")
    second = ModelCallTrace.create(provider="hive", model="m", run_id="run-1")

    assert first is not None and second is not None
    assert first.path == second.path
    assert first.call_id != second.call_id


def test_safe_endpoint_drops_query_and_userinfo() -> None:
    assert safe_endpoint("https://user:secret@example.com/api?token=private") == (
        "https://example.com/api"
    )


@pytest.mark.asyncio
async def test_capture_stream_persists_partial_response_on_provider_failure(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("FINAI_MODEL_TRACE", "full")
    monkeypatch.setenv("FINAI_MODEL_TRACE_DIR", str(tmp_path))
    trace = ModelCallTrace.create(provider="hive", model="m", run_id="run-partial")
    assert trace is not None

    async def events():
        yield {"event": "token", "data": "partial"}
        yield {"event": "provider_failed", "data": {"phase": "stream"}}
        raise TimeoutError("provider timed out")

    with pytest.raises(TimeoutError):
        async for _ in capture_stream(trace, events()):
            pass

    records = read_trace(trace.path)
    failed = next(record for record in records if record["event"] == "call.failed")
    assert failed["payload"]["text"] == "partial"
    assert failed["payload"]["provider_events"] == [
        {"event": "provider_failed", "data": {"phase": "stream"}}
    ]


@pytest.mark.asyncio
async def test_agent_loop_records_end_to_end_provider_call_trace(
    tmp_path, monkeypatch
) -> None:
    from app.core.agent_loop import AgentLoop, AgentLoopConfig
    from app.models.request_models import Message
    from app.services.hive_service import HiveService

    monkeypatch.setenv("FINAI_MODEL_TRACE", "full")
    monkeypatch.setenv("FINAI_MODEL_TRACE_DIR", str(tmp_path / "traces"))
    monkeypatch.setattr(settings, "HIVE_API_KEY", "test-key")

    def handler(request):
        return httpx.Response(
            200,
            request=request,
            content=b'data: {"choices":[{"delta":{"content":"grounded answer"}}]}\n\ndata: [DONE]\n\n',
        )

    class Tools:
        def definitions(self):
            return []

        async def execute(self, name, arguments):
            raise AssertionError(f"unexpected tool call: {name} {arguments}")

    service = HiveService(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    conversation_id = uuid4()
    loop = AgentLoop(
        service,
        Tools(),
        config=AgentLoopConfig(model="trace-test-model", answer_contract="freeform"),
    )
    events = [
        event
        async for event in loop.run(
            [Message(role="user", content="Say grounded answer")],
            conversation_id=conversation_id,
        )
    ]

    run_id = str(events[0].meta.run_id)
    trace_path = next((tmp_path / "traces").glob(f"**/{run_id}.jsonl"))
    records = read_trace(trace_path)
    request = next(record for record in records if record["event"] == "request.attempt")
    completed = next(
        record for record in records if record["event"] == "call.completed"
    )
    assert request["conversation_id"] == str(conversation_id)
    assert any(
        message.get("content") == "Say grounded answer"
        for message in request["payload"]["request_body"]["messages"]
    )
    assert completed["payload"]["text"] == "grounded answer"
    await service.aclose()
