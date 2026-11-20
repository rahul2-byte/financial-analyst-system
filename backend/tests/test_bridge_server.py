"""In-memory JSON-RPC tests for ``BridgeServer`` over ``FakeRepl``."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from app.events.models import (
    EventFactory,
    RunCompleted,
    RunStarted,
    ToolCompleted,
    ToolStarted,
)
from finai.bridge import protocol as p
from finai.bridge.fake import FakeRepl
from finai.bridge.framing import NdjsonWriter
from finai.bridge.server import BridgeServer

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "backend" / "tests" / "fixtures" / "hdfc_run_events.json"


class _Buffer:
    """Collects ``NdjsonWriter`` output as raw bytes and parsed objects."""

    def __init__(self) -> None:
        self.raw: list[bytes] = []

    def write(self, data: bytes) -> int:
        self.raw.append(data)
        return len(data)

    def flush(self) -> None:
        return None

    @property
    def lines(self) -> list[dict[str, Any]]:
        parsed: list[dict[str, Any]] = []
        for chunk in self.raw:
            for line in chunk.splitlines():
                if line.strip():
                    parsed.append(json.loads(line))
        return parsed


def _request(
    request_id: int, method: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}


def _initialize_params() -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "client": {"name": "t", "version": "0"},
        "terminal": {"columns": 80, "rows": 24},
    }


def _run_start_params(
    client_run_id: str, query: str = "HDFC Bank", mode: str = "guided"
) -> dict[str, Any]:
    return {"client_run_id": client_run_id, "query": query, "mode": mode}


def _server(
    events: list[Any], *, delay_ms: int = 0
) -> tuple[BridgeServer, _Buffer]:
    repl = FakeRepl(events, session_id="fake-session", delay_ms=delay_ms)
    buffer = _Buffer()
    server = BridgeServer(lambda: repl, NdjsonWriter(buffer))
    return server, buffer


def _result_for(buffer: _Buffer, request_id: int) -> Any:
    for line in buffer.lines:
        if line.get("id") == request_id and "result" in line:
            return line["result"]
    return None


def _error_for(buffer: _Buffer, request_id: int) -> Any:
    for line in buffer.lines:
        if line.get("id") == request_id and "error" in line:
            return line["error"]
    return None


async def _wait_for_run_event(buffer: _Buffer) -> None:
    for _ in range(200):
        if any(line.get("method") == "run.event" for line in buffer.lines):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("no run.event notification arrived")


def _hdfc_events() -> list[Any]:
    factory = EventFactory(uuid4())
    return [
        factory.make(RunStarted, query="HDFC Bank"),
        factory.make(ToolStarted, tool="data:fetch_fundamentals", tool_id="t1"),
        factory.make(
            ToolCompleted, tool="data:fetch_fundamentals", tool_id="t1", detail="ok"
        ),
        factory.make(RunCompleted, terminal_status="completed", duration_ms=100.0),
    ]


@pytest.mark.asyncio
async def test_initialize_returns_session_info() -> None:
    server, buffer = _server([])
    await server._dispatch(_request(1, "initialize", _initialize_params()))
    result = _result_for(buffer, 1)
    assert result is not None
    assert result["protocol_version"] == 1
    assert result["mode"] == "guided"
    assert result["session"]["id"] == "fake-session"


@pytest.mark.asyncio
async def test_run_emits_events_and_completed() -> None:
    events = _hdfc_events()
    server, buffer = _server(events)
    await server._dispatch(_request(1, "initialize", _initialize_params()))
    assert _result_for(buffer, 1) is not None

    await server._dispatch(
        _request(2, "run.start", _run_start_params("r1"))
    )
    assert _result_for(buffer, 2) == {"accepted": True}

    task = server._run_task
    assert task is not None
    await asyncio.wait_for(task, 2)

    run_events = [line for line in buffer.lines if line.get("method") == "run.event"]
    assert [line["params"]["event"]["type"] for line in run_events] == [
        "run.started",
        "tool.started",
        "tool.completed",
        "run.completed",
    ]
    tool_event = run_events[1]["params"]
    assert tool_event["display"]["label"] == "Fetching fundamentals"
    assert tool_event["display"]["noun"] == "fundamentals"

    finished = [line for line in buffer.lines if line.get("method") == "run.finished"]
    assert len(finished) == 1
    params = finished[0]["params"]
    assert params["outcome"] == "completed"
    assert params["run_id"] == str(events[0].meta.run_id)
    assert params["artifact_path"] is None
    assert params["message"] is None


@pytest.mark.asyncio
async def test_cancel_mid_run_finishes_cancelled() -> None:
    server, buffer = _server(_hdfc_events(), delay_ms=100)
    await server._dispatch(_request(1, "initialize", _initialize_params()))
    await server._dispatch(_request(2, "run.start", _run_start_params("r1")))
    await _wait_for_run_event(buffer)

    await server._dispatch(_request(3, "run.cancel", {"client_run_id": "r1"}))
    assert _result_for(buffer, 3) == {"cancelled": True}

    task = server._run_task
    assert task is not None
    await asyncio.wait_for(task, 2)
    finished = [line for line in buffer.lines if line.get("method") == "run.finished"]
    assert len(finished) == 1
    assert finished[0]["params"]["outcome"] == "cancelled"


@pytest.mark.asyncio
async def test_second_run_start_is_refused_while_running() -> None:
    factory = EventFactory(uuid4())
    events = [
        factory.make(RunStarted, query="HDFC Bank"),
        factory.make(RunCompleted, terminal_status="completed"),
    ]
    server, buffer = _server(events, delay_ms=50)
    await server._dispatch(_request(1, "initialize", _initialize_params()))
    await server._dispatch(_request(2, "run.start", _run_start_params("r1")))
    assert _result_for(buffer, 2) == {"accepted": True}

    await server._dispatch(_request(3, "run.start", _run_start_params("r2")))
    error = _error_for(buffer, 3)
    assert error is not None
    assert error["code"] == p.RUN_IN_PROGRESS

    task = server._run_task
    assert task is not None
    task.cancel()


@pytest.mark.asyncio
async def test_unknown_method_is_32601() -> None:
    server, buffer = _server([])
    await server._dispatch(_request(1, "initialize", _initialize_params()))
    await server._dispatch(_request(9, "no.such.method", {"x": 1}))
    error = _error_for(buffer, 9)
    assert error is not None
    assert error["code"] == p.METHOD_NOT_FOUND
    assert "no.such.method" in error["message"]


@pytest.mark.asyncio
async def test_bad_params_are_32602() -> None:
    server, buffer = _server([])
    await server._dispatch(_request(1, "initialize", _initialize_params()))
    bad = _request(10, "run.start", {"client_run_id": "r", "query": "q", "mode": "turbo"})
    await server._dispatch(bad)
    error = _error_for(buffer, 10)
    assert error is not None
    assert error["code"] == p.INVALID_PARAMS


@pytest.mark.asyncio
async def test_malformed_line_reports_32700_and_server_continues() -> None:
    server, buffer = _server([])
    reader = asyncio.StreamReader()
    lines = [
        b"{not json}\n",
        json.dumps(_request(1, "initialize", _initialize_params())).encode() + b"\n",
        json.dumps(_request(2, "shutdown", {})).encode() + b"\n",
    ]
    reader.feed_data(b"".join(lines))
    reader.feed_eof()
    await server.serve(reader)

    output = buffer.lines
    assert output[0]["error"]["code"] == p.PARSE_ERROR
    assert output[0].get("id") is None
    assert any(line.get("id") == 1 and "result" in line for line in output)
    assert any(line.get("id") == 2 and "result" in line for line in output)


@pytest.mark.asyncio
async def test_stdin_eof_stops_server_and_cancels_run() -> None:
    server, buffer = _server(_hdfc_events(), delay_ms=100)
    reader = asyncio.StreamReader()
    reader.feed_data(
        json.dumps(_request(1, "initialize", _initialize_params())).encode() + b"\n"
    )
    reader.feed_data(
        json.dumps(_request(2, "run.start", _run_start_params("r1"))).encode() + b"\n"
    )
    reader.feed_eof()
    await server.serve(reader)

    task = server._run_task
    assert task is not None
    assert task.done()
    finished = [line for line in buffer.lines if line.get("method") == "run.finished"]
    assert len(finished) == 1
    assert finished[0]["params"]["outcome"] == "cancelled"


def test_subprocess_fake_bridge_stdout_is_jsonrpc(tmp_path: Path) -> None:
    payload = "".join(
        json.dumps(request) + "\n"
        for request in (
            _request(1, "initialize", _initialize_params()),
            _request(2, "shutdown", {}),
        )
    )
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT / "backend"))
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "finai.bridge",
            "--fake-events",
            str(FIXTURE),
            "--data-dir",
            str(tmp_path),
        ],
        input=payload,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, "no protocol output on stdout"
    seen_ids: set[int] = set()
    for line in lines:
        obj = json.loads(line)
        assert obj["jsonrpc"] == "2.0"
        assert ("result" in obj) or ("error" in obj)
        if "id" in obj:
            seen_ids.add(obj["id"])
    assert {1, 2} <= seen_ids


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["full", "partial", "lookup"])
async def test_run_finished_carries_structured_report(kind: str) -> None:
    from finai.bridge.fake_report import fake_events, fake_material

    events = fake_events(FakeRepl.load_events(FIXTURE), kind)  # type: ignore[arg-type]
    repl = FakeRepl(events, material=fake_material(kind))  # type: ignore[arg-type]
    buffer = _Buffer()
    server = BridgeServer(lambda: repl, NdjsonWriter(buffer))
    await server._dispatch(_request(1, "initialize", _initialize_params()))
    await server._dispatch(_request(2, "run.start", _run_start_params("r1")))
    task = server._run_task
    assert task is not None
    await asyncio.wait_for(task, 5)
    finished = [line for line in buffer.lines if line.get("method") == "run.finished"]
    params = p.RunFinishedParams.model_validate(finished[0]["params"])
    assert params.report is not None and params.report.kind == (
        "lookup" if kind == "lookup" else "report"
    )
    assert params.evidence_status == ("limited" if kind == "partial" else "complete")
    assert params.evidence_availability


@pytest.mark.asyncio
async def test_run_finished_without_material_has_null_report() -> None:
    server, buffer = _server(_hdfc_events())
    await server._dispatch(_request(1, "initialize", _initialize_params()))
    await server._dispatch(_request(2, "run.start", _run_start_params("r1")))
    task = server._run_task
    assert task is not None
    await asyncio.wait_for(task, 2)
    finished = [line for line in buffer.lines if line.get("method") == "run.finished"]
    assert finished[0]["params"]["report"] is None
