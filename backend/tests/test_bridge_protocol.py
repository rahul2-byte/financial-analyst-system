"""Contract tests for the TypeScript bridge protocol models and schemas."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args
from uuid import uuid4

import pytest
from app.events.models import EventMeta, ResearchEvent, RunStarted
from finai.bridge import PROTOCOL_VERSION
from finai.bridge import protocol as p
from finai.bridge.schema import (
    PROTOCOL_FILE,
    RESEARCH_EVENT_FILE,
    export_schemas,
)
from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_SCHEMA_DIR = REPO_ROOT / "protocol" / "schema"


def _meta(sequence: int = 1) -> EventMeta:
    return EventMeta(
        event_id=uuid4(),
        run_id=uuid4(),
        conversation_id=uuid4(),
        sequence=sequence,
        occurred_at=datetime.now(UTC),
    )


def _session() -> p.SessionInfo:
    return p.SessionInfo(
        id="a1b2c3",
        title="New research session",
        message_count=0,
        run_count=0,
    )


def _summary() -> p.SessionSummary:
    return p.SessionSummary(
        id="a1b2c3",
        title="HDFC Bank fundamentals",
        message_count="2",  # type: ignore[arg-type]
        run_count="1",  # type: ignore[arg-type]
        last_status="completed",
        last_activity="2026-01-01T00:00:00Z",
    )


def _display() -> p.Display:
    return p.Display(
        label="Fetched stock data",
        noun="stock data",
        detail="close 1,234",
        failure_detail=None,
        notice=None,
        friendly=None,
        sources=[
            p.DisplaySource(
                label="Yahoo Finance · quote · HDFCBANK.NS",
                url="https://example.test/quote/HDFCBANK.NS",
                host="example.test",
            )
        ],
        candidates=[
            p.DisplayCandidate(symbol="HDFCBANK.NS", name="HDFC Bank", exchange="NSE")
        ],
        lines=["Which HDFC entity did you mean?"],
        review_unavailable=False,
        review_note=None,
        instrument="HDFCBANK.NS",
        failed_nouns=[],
    )


def _run_event_params() -> p.RunEventParams:
    return p.RunEventParams(
        client_run_id="6f1e4d3c",
        event=RunStarted(meta=_meta(), query="HDFC Bank fundamentals"),
        display=_display(),
    )


def _report_view() -> p.ReportView:
    from finai.bridge.fake_report import fake_material
    from finai.report_view import build_report_view

    view = build_report_view(fake_material("full"))
    assert view is not None
    return view


def _protocol_instances() -> dict[type[BaseModel], BaseModel]:
    view = _report_view()
    assert view.instrument and view.quote and view.sparkline
    return {
        p.ReportInstrument: view.instrument,
        p.ReportQuote: view.quote,
        p.ReportSparkline: view.sparkline,
        p.ReportSourceStatus: view.evidence.sources[0],
        p.ReportEvidence: view.evidence,
        p.ReportKeyFigure: view.key_figures[0],
        p.ReportSignal: view.signals[0],
        p.ReportDriver: view.drivers[0],
        p.ReportRisk: view.risks[0],
        p.ReportSource: view.sources[0],
        p.ReportView: view,
        p.ClientInfo: p.ClientInfo(name="finai-tui", version="0.1.0"),
        p.TerminalInfo: p.TerminalInfo(columns=120, rows=40),
        p.ModelInfo: p.ModelInfo(id="model-a", fallback_id="model-b"),
        p.SessionInfo: _session(),
        p.SessionSummary: _summary(),
        p.DisplaySource: p.DisplaySource(
            label="Source", url="https://example.test/a", host=None
        ),
        p.DisplayCandidate: p.DisplayCandidate(
            symbol="HDFCBANK.NS", name="HDFC Bank", exchange="NSE"
        ),
        p.Display: _display(),
        p.InitializeParams: p.InitializeParams(
            protocol_version=1,
            client=p.ClientInfo(name="finai-tui", version="0.1.0"),
            terminal=p.TerminalInfo(columns=120, rows=40),
        ),
        p.InitializeResult: p.InitializeResult(
            protocol_version=1,
            server_version="0.1.0",
            session=_session(),
            mode="guided",
            data_dir=".finai",
            model=p.ModelInfo(id="model-a"),
        ),
        p.RunStartParams: p.RunStartParams(
            client_run_id="6f1e4d3c",
            query="HDFC Bank fundamentals",
            mode="guided",
        ),
        p.RunStartResult: p.RunStartResult(),
        p.RunCancelParams: p.RunCancelParams(client_run_id="6f1e4d3c"),
        p.RunCancelResult: p.RunCancelResult(cancelled=False),
        p.SessionNewParams: p.SessionNewParams(),
        p.SessionNewResult: p.SessionNewResult(session=_session()),
        p.SessionResumeParams: p.SessionResumeParams(id_prefix="a1b2"),
        p.SessionResumeResult: p.SessionResumeResult(session=_session()),
        p.SessionListParams: p.SessionListParams(),
        p.SessionListResult: p.SessionListResult(sessions=[_summary()]),
        p.SessionHistoryParams: p.SessionHistoryParams(),
        p.SessionHistoryResult: p.SessionHistoryResult(queries=["q1", "q2"]),
        p.ContextInfoParams: p.ContextInfoParams(),
        p.ContextInfoResult: p.ContextInfoResult.model_validate(
            {"used_tokens": 1024, "limit": 8192}
        ),
        p.ContextCompactParams: p.ContextCompactParams(),
        p.ContextCompactResult: p.ContextCompactResult.model_validate(
            {"compacted_messages": 4, "estimated_tokens": 900}
        ),
        p.TraceTailParams: p.TraceTailParams(),
        p.TraceTailResult: p.TraceTailResult(
            records=[{"event_type": "run.started", "sequence": 1}],
            ledger_path=".finai/sessions/a1b2/events.v1.jsonl",
        ),
        p.ShutdownParams: p.ShutdownParams(),
        p.ShutdownResult: p.ShutdownResult(),
        p.RunEventParams: _run_event_params(),
        p.RunFinishedParams: p.RunFinishedParams(
            client_run_id="6f1e4d3c",
            outcome="completed",
            run_id=uuid4(),
            artifact_path=".finai/sessions/a1b2/runs/run.json",
            message=None,
        ),
        p.BridgeLogParams: p.BridgeLogParams(level="info", message="ready"),
        p.ErrorObject: p.ErrorObject(
            code=p.INVALID_PARAMS, message="Invalid params", data={"field": "mode"}
        ),
        p.Request: p.Request(id=1, method="initialize", params={"protocol_version": 1}),
        p.Response: p.Response(id=1, result={"accepted": True}),
        p.Notification: p.Notification(
            method="run.event", params={"client_run_id": "6f1e4d3c"}
        ),
    }


def test_protocol_version() -> None:
    assert PROTOCOL_VERSION == 1


def test_error_codes_are_stable() -> None:
    assert p.PARSE_ERROR == -32700
    assert p.INVALID_REQUEST == -32600
    assert p.METHOD_NOT_FOUND == -32601
    assert p.INVALID_PARAMS == -32602
    assert p.INTERNAL_ERROR == -32603
    assert p.RUN_IN_PROGRESS == -32001
    assert p.NO_ACTIVE_RUN == -32002
    assert p.SESSION_NOT_FOUND == -32003
    assert p.PROTOCOL_MISMATCH == -32004


def test_every_protocol_model_has_a_round_trip_instance() -> None:
    instances = _protocol_instances()
    assert set(instances) == set(p.PROTOCOL_MODELS)


@pytest.mark.parametrize(
    "model",
    p.PROTOCOL_MODELS,
    ids=[model.__name__ for model in p.PROTOCOL_MODELS],
)
def test_protocol_model_round_trip(model: type[BaseModel]) -> None:
    instance = _protocol_instances()[model]
    dumped = instance.model_dump(mode="json")
    assert model.model_validate(dumped) == instance


@pytest.mark.parametrize(
    "factory",
    [
        lambda: p.RunStartParams(
            client_run_id="6f1e4d3c", query="q", mode="guided", unexpected=True
        ),
        lambda: p.RunStartParams(client_run_id="6f1e4d3c", query="q", mode="turbo"),
        lambda: p.InitializeParams(
            protocol_version=1,
            client=p.ClientInfo(name="t", version="0"),
            terminal=p.TerminalInfo(columns=80, rows=24),
            unexpected=True,
        ),
        lambda: p.ClientInfo(name="t", version="0", unexpected=True),
        lambda: p.Request(id=1, method="initialize", params={}, unexpected=True),
        lambda: p.Request(jsonrpc="1.0", id=1, method="initialize"),
    ],
    ids=[
        "extra-param-field",
        "wrong-mode-literal",
        "extra-initialize-field",
        "extra-nested-client-field",
        "extra-envelope-field",
        "wrong-jsonrpc-version",
    ],
)
def test_invalid_params_are_rejected(factory: Any) -> None:
    with pytest.raises(ValidationError):
        factory()


def test_schema_files_are_fresh(tmp_path: Path) -> None:
    generated = export_schemas(tmp_path)
    assert [path.name for path in generated] == [
        RESEARCH_EVENT_FILE,
        PROTOCOL_FILE,
    ]
    for path in generated:
        committed = COMMITTED_SCHEMA_DIR / path.name
        assert committed.exists(), f"missing committed schema {committed}"
        assert path.read_bytes() == committed.read_bytes(), (
            f"{committed} is stale; run "
            "PYTHONPATH=backend uv run --offline python -m finai.bridge.schema "
            "--out protocol/schema"
        )


def _literal_values(node: object) -> set[str]:
    values: set[str] = set()
    if isinstance(node, dict):
        const = node.get("const")
        if isinstance(const, str):
            values.add(const)
        enum = node.get("enum")
        if isinstance(enum, list):
            values.update(item for item in enum if isinstance(item, str))
        for child in node.values():
            values |= _literal_values(child)
    elif isinstance(node, list):
        for child in node:
            values |= _literal_values(child)
    return values


def _research_event_types() -> set[str]:
    union = get_args(ResearchEvent)[0]
    members = get_args(union)
    assert members, "ResearchEvent union is empty"
    types: set[str] = set()
    for member in members:
        default = member.model_fields["type"].default
        assert isinstance(default, str)
        types.add(default)
    return types


def test_research_event_schema_contains_all_types() -> None:
    event_types = _research_event_types()
    assert len(event_types) == 27

    schema = json.loads(
        (COMMITTED_SCHEMA_DIR / RESEARCH_EVENT_FILE).read_text(encoding="utf-8")
    )
    schema_literals = _literal_values(schema)
    missing = event_types - schema_literals
    assert not missing, f"event types missing from schema: {sorted(missing)}"


def test_protocol_schema_contains_every_model() -> None:
    schema = json.loads(
        (COMMITTED_SCHEMA_DIR / PROTOCOL_FILE).read_text(encoding="utf-8")
    )
    defs = schema["$defs"]
    missing = {model.__name__ for model in p.PROTOCOL_MODELS} - set(defs)
    assert not missing, f"models missing from protocol schema: {sorted(missing)}"
    assert "ResearchEvent" in defs or "RunEventParams" in defs
