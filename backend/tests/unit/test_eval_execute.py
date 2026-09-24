import asyncio
import json
from argparse import Namespace
from types import SimpleNamespace

import pytest

import evals.execute as execute_module
from evals.execute import (
    _benchmark_provenance,
    _loop_config,
    _stage_timings,
    _write_jsonl,
    execute_live_case,
    failed_artifact,
    result_record,
    retry_cases,
)


def test_benchmark_provenance_satisfies_evidence_accounting() -> None:
    from app.core.agent_loop.evidence import valid_provenance

    provenance = _benchmark_provenance(
        {
            "instrument_key": "NSE_EQ|INE000000001",
            "trading_symbol": "ABC",
            "snapshot_id": "a" * 64,
            "retrieved_at": "2026-09-22T10:00:00+05:30",
            "source_url": "https://api.upstox.com/v3/historical-candle/example",
        },
        ingested_at="2026-09-23T10:00:00+05:30",
    )

    assert valid_provenance({"provenance": provenance})


def test_result_record_preserves_case_identity_and_structured_output() -> None:
    artifact = {
        "case_id": "real-v1-001",
        "terminal_status": "completed_with_limited_evidence",
        "claims": [{"claim_id": "claim-1"}],
        "citations": [{"citation_id": "citation-1"}],
        "report_validation": {"status": "structured"},
        "metadata": {},
    }

    assert result_record(artifact) == {
        "id": "real-v1-001",
        "terminal_status": "completed_with_limited_evidence",
        "claims": [{"claim_id": "claim-1"}],
        "citations": [{"citation_id": "citation-1"}],
        "valid_plan": True,
        "duration_ms": None,
        "timings_ms": {},
        "data_collection_duration_ms": None,
        "model_id": None,
    }


def test_failed_artifact_is_judgeable() -> None:
    artifact = failed_artifact({"case_id": "real-v1-002", "query": "Q"}, "timeout")

    assert artifact["terminal_status"] == "failed"
    assert artifact["failure_details"][0]["message"] == "timeout"
    assert result_record(artifact)["id"] == "real-v1-002"


def test_live_executor_uses_explicit_default_and_escalation_models() -> None:
    config = _loop_config({}, "test-model")

    assert config.max_tokens == 8192
    assert config.publish_reports is False
    assert config.model == "test-model"
    assert config.repair_model == "test-model"
    assert config.escalation_model == "test-model"

    escalated = _loop_config({}, "gpt-5.6-luna", "gpt-6-luna")
    assert escalated.model == "gpt-5.6-luna"
    assert escalated.repair_model == "gpt-5.6-luna"
    assert escalated.escalation_model == "gpt-6-luna"

    benchmark = _loop_config(
        {"configuration": {"allowed_tools": ["data:fetch_stock_data"]}},
        "gpt-5.6-luna",
        "gpt-6-luna",
    )
    assert benchmark.allowed_tools == frozenset({"data:fetch_stock_data"})


def test_checkpoint_writer_persists_completed_rows(tmp_path) -> None:
    target = tmp_path / "results.jsonl"

    _write_jsonl(target, [{"id": "case-1"}])

    assert target.read_text(encoding="utf-8") == '{"id": "case-1"}\n'


def test_checkpoint_writer_keeps_previous_snapshot_if_atomic_replace_fails(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / "results.jsonl"
    target.write_text('{"id": "previous"}\n')

    def fail_replace(source, destination):
        raise OSError("simulated interruption during snapshot update")

    monkeypatch.setattr(execute_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated interruption"):
        _write_jsonl(target, [{"id": "new"}])

    assert target.read_text(encoding="utf-8") == '{"id": "previous"}\n'


def test_live_execution_resumes_from_completed_case_artifacts(tmp_path, monkeypatch):
    import app.services.chatgpt_codex_service as codex_service
    from app.services.chatgpt_codex_service import CodexCredentialStore

    from evals import upstox_benchmark

    manifest = tmp_path / "cases.jsonl"
    cases = [
        {"case_id": f"case-{index}", "query": f"query-{index}"} for index in range(1, 4)
    ]
    manifest.write_text("".join(json.dumps(case) + "\n" for case in cases))
    output_dir = tmp_path / "run" / "artifacts"
    result_path = tmp_path / "run" / "results.jsonl"
    events_path = tmp_path / "run" / "events.jsonl"
    metrics_path = tmp_path / "run" / "metrics.jsonl"
    calls = []
    interrupt = {"enabled": True}

    monkeypatch.setattr(
        CodexCredentialStore, "load", lambda self: {"access_token": "available"}
    )
    monkeypatch.setattr(upstox_benchmark, "validate_cases", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        upstox_benchmark, "validate_archive_cases", lambda *args, **kwargs: []
    )

    class FakeService:
        def __init__(self, **kwargs):
            del kwargs

        async def aclose(self):
            return None

    monkeypatch.setattr(
        execute_module,
        "build_runtime_resources",
        lambda **kwargs: SimpleNamespace(
            llm_service=kwargs["llm_service"],
            provider_archive=kwargs["provider_archive"],
        ),
    )
    monkeypatch.setattr(codex_service, "ChatGPTCodexService", FakeService)

    async def fake_execute_case(case, **kwargs):
        case_id = case["case_id"]
        calls.append(case_id)
        if interrupt["enabled"] and case_id == "case-3":
            await asyncio.Event().wait()
        if interrupt["enabled"] and case_id == "case-2":
            raise RuntimeError("simulated process interruption")
        artifact = {
            "artifact_version": "v2",
            "case_id": case_id,
            "terminal_status": "success",
            "claims": [],
            "citations": [],
            "report_validation": {"status": "structured"},
            "metadata": {"duration_ms": 1, "timings_ms": {}},
        }
        return artifact, [
            {"event_type": "run.completed", "payload": {"case_id": case_id}}
        ]

    monkeypatch.setattr(execute_module, "execute_live_case", fake_execute_case)

    def args(*, resume):
        return Namespace(
            cases=manifest,
            output_dir=output_dir,
            results=result_path,
            events=events_path,
            metrics=metrics_path,
            archive_root=tmp_path / "archive",
            model="gpt-default",
            escalation_model="gpt-escalation",
            retry_of=None,
            attempt_type="first_attempt",
            limit=None,
            expected_cases=3,
            concurrency=1,
            case_timeout_seconds=120,
            resume=resume,
            allow_live=True,
        )

    async def interrupted_run():
        with pytest.raises(RuntimeError, match="simulated process interruption"):
            await execute_module.execute(args(resume=False))

    asyncio.run(interrupted_run())
    first_attempt_calls = calls.copy()
    assert (output_dir / "case-1.json").exists()
    assert not (output_dir / "case-3.json").exists()

    # Simulate an interrupted JSONL snapshot update. Resume rebuilds it from the
    # durable per-case artifact and its co-located event ledger.
    result_path.write_text("partial jsonl")
    events_path.write_text("partial jsonl")
    changed_run = args(resume=True)
    changed_run.model = "different-model"
    with pytest.raises(ValueError, match="cannot resume"):
        asyncio.run(execute_module.execute(changed_run))
    interrupt["enabled"] = False
    assert asyncio.run(execute_module.execute(args(resume=True))) == 0

    assert calls[len(first_attempt_calls) :] == ["case-2", "case-3"]
    results = [json.loads(line) for line in result_path.read_text().splitlines()]
    events = [json.loads(line) for line in events_path.read_text().splitlines()]
    assert [row["id"] for row in results] == ["case-1", "case-2", "case-3"]
    assert [row["payload"]["case_id"] for row in events] == [
        "case-1",
        "case-2",
        "case-3",
    ]


def test_stage_timings_keep_provider_and_tool_boundaries_separate() -> None:
    timings = _stage_timings(
        [
            {
                "event_type": "provider.completed",
                "payload": {"duration_ms": 800, "first_token_ms": 250},
            },
            {"event_type": "tool.completed", "payload": {"duration_ms": 40}},
            {"event_type": "provider.completed", "payload": {"duration_ms": 600}},
        ]
    )

    assert timings == {
        "provider_total_ms": 1400,
        "provider_call_count": 2,
        "time_to_first_token_ms": [250.0],
        "tool_total_ms": 40,
        "tool_call_count": 1,
    }


def test_retry_selector_keeps_only_first_attempt_failures_and_partials() -> None:
    cases = [{"case_id": f"case-{index}"} for index in range(3)]
    selected = retry_cases(
        cases,
        [
            {"id": "case-0", "terminal_status": "success"},
            {"id": "case-1", "terminal_status": "partial"},
            {"id": "case-2", "terminal_status": "failed"},
        ],
    )

    assert [case["case_id"] for case in selected] == ["case-1", "case-2"]


def test_live_executor_persists_validated_structured_report_before_rendering(
    tmp_path,
) -> None:
    from app.core.resources import RuntimeResources
    from app.observability.provider_archive import ProviderArchive

    tool_call = {
        "index": 0,
        "id": "call-price",
        "type": "function",
        "function": {
            "name": "data:fetch_stock_data",
            "arguments": '{"ticker":"ABC"}',
        },
    }
    report = (
        '{"executive_summary":"Close [[fact:upstox_historical_candle:data.latest.close]].",'
        '"key_drivers":["Returned market observation."],'
        '"detailed_analysis":"Close [[fact:upstox_historical_candle:data.latest.close]].",'
        '"risks":["Historical observation only."],"final_view":"Review.",'
        '"claims":[{"claim_id":"close","text":"Close '
        '[[fact:upstox_historical_candle:data.latest.close]].","importance":"major",'
        '"evidence_refs":["citation-upstox"],'
        '"numeric_refs":["upstox_historical_candle:data.latest.close"]}],'
        '"citations":[{"citation_id":"citation-upstox",'
        '"source_id":"upstox_historical_candle"}]}'
    )

    class Model:
        def __init__(self):
            self.responses = [
                [
                    {
                        "event": "chunk",
                        "data": {"choices": [{"delta": {"tool_calls": [tool_call]}}]},
                    }
                ],
                [{"event": "token", "data": report}],
            ]
            self.requests = []

        def generate_stream(self, messages, model, **kwargs):
            self.requests.append(messages)
            del model, kwargs
            response = self.responses.pop(0)

            async def stream():
                for frame in response:
                    yield frame

            return stream()

    case = {
        "case_id": "pilot-structured-report",
        "query": "What is ABC closing price?",
        "trading_symbol": "ABC",
        "trading_date": "2026-09-22",
        "instrument_key": "NSE_EQ|INE000000001",
        "snapshot_id": "a" * 64,
        "retrieved_at": "2026-09-22T10:00:00+05:30",
        "source_url": "https://api.upstox.com/v3/historical-candle/example",
        "frozen_candle": {
            "timestamp": "2026-09-22T10:00:00+05:30",
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "volume": 100,
        },
        "configuration": {
            "publish_reports": True,
            "allowed_tools": ["data:fetch_stock_data"],
        },
    }
    resources = RuntimeResources(
        llm_service=Model(),
        yf_fetcher=object(),
        provider_archive=ProviderArchive(tmp_path / "archive"),
    )

    artifact, events = asyncio.run(
        execute_live_case(case, resources=resources, model="gpt-5.6-luna")
    )

    assert events
    assert artifact["report_validation"] == {
        "status": "structured",
        "publication_status": "passed",
        "reasons": [],
    }
    assert artifact["claims"][0]["claim_id"] == "close"
    assert artifact["citations"][0]["source_id"] == "upstox_historical_candle"
    tool_result = next(
        json.loads(message.content)
        for message in resources.llm_service.requests[-1]
        if message.role == "tool"
    )
    assert tool_result["benchmark_context"] == {
        "requested_trading_date": "2026-09-22",
        "date_matches": True,
    }
