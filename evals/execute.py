"""Execute approved benchmark cases and persist judgeable run artifacts."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import settings
from app.core.agent_loop import AgentLoop, AgentLoopConfig, FinancialToolRunner
from app.core.resources import RuntimeResources, build_runtime_resources
from app.core.skills import SkillRegistry
from app.events.models import ResearchEvent, RunCompleted, TextDelta, ToolCompleted
from app.models.request_models import Message
from app.observability.provider_archive import ProviderArchive, ProviderSnapshot

from evals.offline import load_cases, write_result_artifact


def _stage_timings(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Separate provider time, time to first token, and tool time."""
    provider_ms = []
    first_token_ms = []
    tool_ms = []
    for record in records:
        payload = record.get("payload", {})
        payload = payload if isinstance(payload, dict) else {}
        if record.get("event_type") == "provider.completed":
            if isinstance(payload.get("duration_ms"), (int, float)):
                provider_ms.append(float(payload["duration_ms"]))
            if isinstance(payload.get("first_token_ms"), (int, float)):
                first_token_ms.append(float(payload["first_token_ms"]))
        elif record.get("event_type") == "tool.completed" and isinstance(
            payload.get("duration_ms"), (int, float)
        ):
            tool_ms.append(float(payload["duration_ms"]))
    return {
        "provider_total_ms": round(sum(provider_ms), 2),
        "provider_call_count": len(provider_ms),
        "time_to_first_token_ms": first_token_ms,
        "tool_total_ms": round(sum(tool_ms), 2),
        "tool_call_count": len(tool_ms),
    }


def result_record(artifact: dict[str, Any]) -> dict[str, Any]:
    """Return the metric-facing subset of an executed artifact."""
    metadata = artifact.get("metadata", {})
    return {
        "id": artifact["case_id"],
        "terminal_status": artifact["terminal_status"],
        "claims": artifact["claims"],
        "citations": artifact["citations"],
        "valid_plan": artifact["report_validation"].get("status") == "structured",
        "duration_ms": metadata.get("duration_ms"),
        "timings_ms": metadata.get("timings_ms", {}),
        "data_collection_duration_ms": metadata.get("data_collection_duration_ms"),
        "model_id": metadata.get("model_id"),
    }


def _latency_summary(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "sample_count": len(ordered),
        "p50": round(ordered[max(0, ceil(len(ordered) * 0.50) - 1)], 2)
        if ordered
        else None,
        "p95": round(ordered[max(0, ceil(len(ordered) * 0.95) - 1)], 2)
        if ordered
        else None,
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    content = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    _atomic_write_text(path, content)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _run_state(
    cases: list[dict[str, Any]],
    first_attempt_results: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    manifest = json.dumps(cases, sort_keys=True, separators=(",", ":"))
    first_results = json.dumps(
        first_attempt_results, sort_keys=True, separators=(",", ":")
    )
    identity = {
        "schema_version": 1,
        "case_ids": [str(case["case_id"]) for case in cases],
        "cases_sha256": hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
        "first_attempt_results_sha256": hashlib.sha256(
            first_results.encode("utf-8")
        ).hexdigest(),
        "model": args.model,
        "escalation_model": args.escalation_model,
        "attempt_type": args.attempt_type,
        "concurrency": args.concurrency,
        "case_timeout_seconds": args.case_timeout_seconds,
    }
    fingerprint = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return {
        **identity,
        "run_signature": hashlib.sha256(fingerprint.encode("utf-8")).hexdigest(),
    }


def _load_completed_artifacts(
    output_dir: Path, state: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    expected_ids = set(state["case_ids"])
    completed: dict[str, dict[str, Any]] = {}
    for path in output_dir.glob("*.json"):
        if path.name == "run-state.json":
            continue
        case_id = path.stem
        if case_id not in expected_ids:
            raise ValueError(f"unexpected artifact in resume directory: {path}")
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid completed-case artifact: {path}") from exc
        if (
            not isinstance(artifact, dict)
            or artifact.get("case_id") != case_id
            or artifact.get("run_signature") != state["run_signature"]
            or not isinstance(artifact.get("event_ledger"), list)
            or any(not isinstance(record, dict) for record in artifact["event_ledger"])
            or not isinstance(artifact.get("claims"), list)
            or not isinstance(artifact.get("citations"), list)
            or not isinstance(artifact.get("report_validation"), dict)
            or not isinstance(artifact.get("metadata"), dict)
        ):
            raise ValueError(f"artifact is not a valid checkpoint for this run: {path}")
        completed[case_id] = artifact
    return completed


def _checkpoint_views(
    cases: list[dict[str, Any]],
    completed: dict[str, dict[str, Any]],
    results_path: Path,
    events_path: Path,
) -> list[dict[str, Any]]:
    ordered = [
        completed[str(case["case_id"])]
        for case in cases
        if str(case["case_id"]) in completed
    ]
    results = [result_record(artifact) for artifact in ordered]
    _write_jsonl(results_path, results)
    _write_jsonl(
        events_path,
        [record for artifact in ordered for record in artifact["event_ledger"]],
    )
    return results


def _benchmark_provenance(case: dict[str, Any], *, ingested_at: str) -> dict[str, Any]:
    return {
        "source": "upstox",
        "dataset": "upstox_historical_candle",
        "instrument": str(case["instrument_key"]),
        "observed_at": case["retrieved_at"],
        "ingested_at": ingested_at,
        "version": str(case["snapshot_id"]),
        "quality_status": "verified",
        "source_url": case["source_url"],
    }


def retry_cases(
    cases: list[dict[str, Any]], first_results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    retry_ids = {
        str(result.get("id"))
        for result in first_results
        if result.get("terminal_status") not in {"success", "completed"}
    }
    return [case for case in cases if str(case.get("case_id")) in retry_ids]


def failed_artifact(case: dict[str, Any], message: str) -> dict[str, Any]:
    """Persist a bounded execution failure as an explicit, judgeable artifact."""
    return {
        "artifact_version": "v1",
        "case_id": str(case["case_id"]),
        "mode": "live",
        "query": str(case["query"]),
        "report": "",
        "terminal_status": "failed",
        "claims": [],
        "citations": [],
        "report_validation": {"status": "unparsed", "reasons": [message]},
        "tool_calls": [],
        "failure_details": [{"type": "execution_failure", "message": message}],
        "provenance": {
            name: case.get(name)
            for name in (
                "snapshot_id",
                "source_url",
                "retrieved_at",
                "content_sha256",
                "usage_permission",
                "permission_basis",
            )
        },
        "metadata": {"event_count": 0},
    }


def _event_record(event: ResearchEvent) -> dict[str, Any]:
    value = event.model_dump(mode="json")
    meta = value.pop("meta")
    event_type = value.pop("type")
    return {
        "schema_version": 1,
        "event_id": meta["event_id"],
        "run_id": meta["run_id"],
        "conversation_id": meta["conversation_id"],
        "sequence": meta["sequence"],
        "occurred_at": meta["occurred_at"],
        "event_type": event_type,
        "payload": value,
        "artifact_refs": [],
    }


def _loop_config(
    case: dict[str, Any], model: str, escalation_model: str | None = None
) -> AgentLoopConfig:
    configuration = case.get("configuration")
    configuration = configuration if isinstance(configuration, dict) else {}
    return AgentLoopConfig(
        model=model,
        mode=str(configuration.get("mode", "guided")),
        repair_model=model,
        escalation_model=escalation_model or model,
        route_plan=case.get("route_plan"),
        max_rounds=int(configuration.get("max_rounds", 12)),
        emergency_max_tool_calls=int(
            configuration.get("emergency_max_tool_calls", 128)
        ),
        max_tokens=int(configuration.get("max_tokens", 8192)),
        report_max_tokens=int(configuration.get("report_max_tokens", 32768)),
        publish_reports=bool(configuration.get("publish_reports", False)),
        allowed_tools=(
            frozenset(configuration["allowed_tools"])
            if configuration.get("allowed_tools")
            else None
        ),
    )


async def execute_live_case(
    case: dict[str, Any],
    *,
    resources: RuntimeResources,
    model: str,
    escalation_model: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run one real agent trajectory and retain its complete emitted ledger."""
    case_id = str(case["case_id"])
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    report = ""
    report_result: dict[str, Any] | None = None
    terminal_status = "failed"
    tool_calls: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    try:
        evidence_payload = {
            "ticker": case["trading_symbol"],
            "period": "1d",
            "interval": "1d",
            "data": [case["frozen_candle"]] if case["frozen_candle"] else [],
            "provenance": _benchmark_provenance(
                case, ingested_at=started_at.isoformat()
            ),
        }
        benchmark_evidence = {
            str(case["trading_symbol"]).upper(): {
                "success": case["frozen_candle"] is not None,
                "data": evidence_payload,
                "provenance": evidence_payload["provenance"],
                "requested_trading_date": str(case["trading_date"]),
                **(
                    {}
                    if case["frozen_candle"] is not None
                    else {
                        "error": (
                            f"No Upstox candle for instrument on {case['trading_date']}"
                        ),
                        "retryable": False,
                    }
                ),
            }
        }
        if resources.provider_archive is None:
            raise RuntimeError("provider archive is required for benchmark evidence")
        evidence_snapshot = resources.provider_archive.store(
            ProviderSnapshot(
                provider="upstox",
                operation="fetch_stock_price",
                payload=evidence_payload,
                fetched_at=started_at,
            )
        )
        evidence_payload["provenance"]["snapshot_hash"] = evidence_snapshot.content_hash
        benchmark_evidence[str(case["trading_symbol"]).upper()]["provenance"] = (
            evidence_payload["provenance"]
        )
        benchmark_evidence[str(case["trading_symbol"]).upper()]["data"][
            "provenance"
        ] = evidence_payload["provenance"]
        loop = AgentLoop(
            resources.llm_service,
            FinancialToolRunner(resources, benchmark_evidence=benchmark_evidence),
            config=_loop_config(case, model, escalation_model),
            skill_registry=SkillRegistry.bundled(),
        )
        async for event in loop.run(
            [Message(role="user", content=str(case["query"]))],
            conversation_id=uuid4(),
        ):
            record = _event_record(event)
            records.append(record)
            if isinstance(event, TextDelta):
                report += event.text
            elif isinstance(event, ToolCompleted):
                tool_calls.append(
                    {
                        "tool": event.tool,
                        "tool_id": event.tool_id,
                        "detail": event.detail,
                        "duration_ms": event.duration_ms,
                    }
                )
            elif isinstance(event, RunCompleted):
                terminal_status = event.terminal_status
            elif event.type in {
                "run.failed",
                "run.cancelled",
                "provider.failed",
                "tool.failed",
            }:
                failures.append(record)
        report_result = loop.last_report_result
    except Exception as exc:  # noqa: BLE001 - persist every live execution failure
        failures.append({"type": type(exc).__name__, "message": str(exc)})
    claims: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    if _loop_config(case, model, escalation_model).publish_reports:
        report_result = report_result or {
            "status": "invalid",
            "draft": None,
            "publication_status": "failed",
            "reasons": ["report_artifact_unavailable"],
        }
        draft_data = report_result.get("draft")
        if isinstance(draft_data, dict):
            claims = list(draft_data.get("claims") or [])
            citations = list(draft_data.get("citations") or [])
        validation = {
            "status": report_result.get("status"),
            "publication_status": report_result.get("publication_status"),
            "reasons": report_result.get("reasons", []),
        }
    else:
        validation = {"status": "not_requested"}
    artifact = {
        "artifact_version": "v1",
        "case_id": case_id,
        "mode": "live",
        "query": case["query"],
        "report": report,
        "terminal_status": terminal_status,
        "claims": claims,
        "citations": citations,
        "report_validation": validation,
        "tool_calls": tool_calls,
        "failure_details": failures,
        "provenance": {
            name: case.get(name)
            for name in (
                "snapshot_id",
                "source_url",
                "retrieved_at",
                "content_sha256",
                "instrument_key",
                "usage_permission",
                "permission_basis",
            )
        },
        "evaluation": {
            "expected_outcome": case.get("expected_outcome"),
            "gold_numbers": case.get("gold_numbers"),
        },
        "metadata": {
            "model_id": model,
            "default_model_id": model,
            "escalation_model_id": escalation_model,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "terminal_status_recorded_at": next(
                (
                    record["occurred_at"]
                    for record in reversed(records)
                    if record.get("event_type") == "run.completed"
                ),
                None,
            ),
            "event_count": len(records),
            "timings_ms": _stage_timings(records),
            "data_collection_duration_ms": case.get("data_collection_duration_ms"),
        },
    }
    return artifact, records


async def execute(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases)
    first_attempt_results = (
        load_cases(args.retry_of) if args.retry_of is not None else []
    )
    if args.attempt_type == "retry" and args.retry_of is None:
        raise ValueError("retry runs require --retry-of with first-attempt results")
    if args.retry_of is not None:
        if args.attempt_type != "retry":
            raise ValueError("--retry-of requires --attempt-type retry")
        cases = retry_cases(cases, first_attempt_results)
    if args.limit is not None:
        cases = cases[: args.limit]
    if not cases:
        raise ValueError("no cases selected")
    from evals.upstox_benchmark import (
        score_artifacts,
        validate_archive_cases,
        validate_cases,
    )

    validation_errors = validate_cases(cases, expected_count=len(cases))
    if validation_errors:
        raise ValueError("invalid benchmark manifest: " + "; ".join(validation_errors))
    archive_errors = validate_archive_cases(cases, args.archive_root)
    if archive_errors:
        raise ValueError("invalid source archive: " + "; ".join(archive_errors))
    expected_cases = args.expected_cases
    if expected_cases is None:
        expected_cases = 150 if args.attempt_type == "first_attempt" else len(cases)
    if len(cases) != expected_cases:
        raise ValueError(f"expected {expected_cases} cases, found {len(cases)}")
    state = _run_state(cases, first_attempt_results, args)
    state_path = args.output_dir / "run-state.json"
    if getattr(args, "resume", False):
        if not state_path.is_file():
            raise ValueError("cannot resume: run-state.json is missing")
        try:
            previous_state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("cannot resume: run-state.json is invalid") from exc
        if previous_state != state:
            raise ValueError(
                "cannot resume: manifest, model, attempt type, concurrency, or timeout changed"
            )
        completed = _load_completed_artifacts(args.output_dir, state)
    else:
        if args.output_dir.exists() and any(args.output_dir.iterdir()):
            raise FileExistsError(
                "artifact output directory must be empty; use --resume to continue a run"
            )
        if args.results.exists() or args.events.exists() or args.metrics.exists():
            raise FileExistsError(
                "output files already exist; use new paths or --resume"
            )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(
            state_path, json.dumps(state, indent=2, sort_keys=True) + "\n"
        )
        completed = {}
    results = _checkpoint_views(cases, completed, args.results, args.events)
    pending_cases = [case for case in cases if str(case["case_id"]) not in completed]
    if getattr(args, "resume", False):
        print(
            f"restored checkpoints: {len(completed)} completed, "
            f"{len(pending_cases)} remaining",
            file=sys.stderr,
            flush=True,
        )
    archive = ProviderArchive(args.archive_root)
    from app.services.chatgpt_codex_service import (
        ChatGPTCodexService,
        CodexCredentialStore,
    )

    credential_store = CodexCredentialStore(
        Path(settings.FINAI_CHATGPT_CODEX_CREDENTIAL_PATH).expanduser()
    )
    if not credential_store.load():
        raise ValueError("ChatGPT Codex credentials unavailable")
    resources = build_runtime_resources(
        llm_service=ChatGPTCodexService(
            fallback=None,
            credential_store=credential_store,
            endpoint=settings.FINAI_CHATGPT_CODEX_API_ENDPOINT,
            timeout_seconds=settings.FINAI_CHATGPT_CODEX_TIMEOUT_SECONDS,
        ),
        provider_archive=archive,
    )
    semaphore = asyncio.Semaphore(args.concurrency)

    async def run_case(
        case: dict[str, Any],
    ) -> dict[str, Any]:
        async with semaphore:
            case_id = str(case.get("case_id") or "")
            if not case_id or not isinstance(case.get("query"), str):
                raise ValueError("each case requires case_id and query")
            target = args.output_dir / f"{case_id}.json"
            if target.exists():
                raise FileExistsError(f"artifact already exists: {target}")
            try:
                artifact, records = await asyncio.wait_for(
                    execute_live_case(
                        case,
                        resources=resources,
                        model=args.model,
                        escalation_model=args.escalation_model,
                    ),
                    timeout=args.case_timeout_seconds,
                )
            except TimeoutError:
                artifact = failed_artifact(
                    case, f"case timed out after {args.case_timeout_seconds} seconds"
                )
                records = []
            artifact["run_signature"] = state["run_signature"]
            artifact["event_ledger"] = records
            write_result_artifact(target, artifact)
            return artifact

    try:
        tasks = [asyncio.create_task(run_case(case)) for case in pending_cases]
        for task in asyncio.as_completed(tasks):
            artifact = await task
            completed[artifact["case_id"]] = artifact
            results = _checkpoint_views(cases, completed, args.results, args.events)
            print(
                f"checkpoint saved: {artifact['case_id']} "
                f"({len(completed)}/{len(cases)} cases)",
                file=sys.stderr,
                flush=True,
            )
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        close = getattr(resources.llm_service, "aclose", None)
        if close is not None:
            await close()
    results = _checkpoint_views(cases, completed, args.results, args.events)
    metrics = {
        "attempt_type": args.attempt_type,
        "attempted": len(cases),
        "completed": sum(
            item["terminal_status"] in {"success", "completed"} for item in results
        ),
        "partial": sum(item["terminal_status"] == "partial" for item in results),
        "limited_evidence": sum(
            item["terminal_status"] == "completed_with_limited_evidence"
            for item in results
        ),
        "failed": sum(item["terminal_status"] == "failed" for item in results),
        "latency_ms": {
            "end_to_end": _latency_summary(
                [
                    float(item["duration_ms"])
                    for item in results
                    if item.get("duration_ms") is not None
                ]
            ),
            "provider_total": _latency_summary(
                [
                    float(item.get("timings_ms", {}).get("provider_total_ms"))
                    for item in results
                    if item.get("timings_ms", {}).get("provider_call_count", 0)
                ]
            ),
            "tool_total": _latency_summary(
                [
                    float(item.get("timings_ms", {}).get("tool_total_ms"))
                    for item in results
                    if item.get("timings_ms", {}).get("tool_call_count", 0)
                ]
            ),
            "time_to_first_token": _latency_summary(
                [
                    float(value)
                    for item in results
                    for value in item.get("timings_ms", {}).get(
                        "time_to_first_token_ms", []
                    )
                ]
            ),
            "data_collection": _latency_summary(
                [
                    float(item["data_collection_duration_ms"])
                    for item in results
                    if item.get("data_collection_duration_ms") is not None
                ]
            ),
        },
    }
    quality = None
    if all(
        case.get("expected_outcome") in {"answer", "evidence_gap"}
        for case in cases
    ):
        quality = score_artifacts(cases, list(completed.values()))
        metrics["deterministic_answer_quality"] = quality
    if args.attempt_type == "retry":
        first_by_id = {str(item["id"]): item for item in first_attempt_results}
        retry_by_id = {str(item["id"]): item for item in results}
        eligible = {
            case_id
            for case_id, item in first_by_id.items()
            if item.get("terminal_status") not in {"success", "completed"}
        }
        recovered = {
            case_id
            for case_id in eligible & retry_by_id.keys()
            if retry_by_id[case_id].get("terminal_status") in {"success", "completed"}
        }
        metrics.update(
            {
                "first_attempt_denominator": len(first_by_id),
                "retry_eligible": len(eligible),
                "recovered_on_retry": len(recovered),
                "unresolved_after_retry": len(eligible - recovered),
                "retry_adjusted_completed": len(first_by_id)
                - len(eligible)
                + len(recovered),
            }
        )
    _write_jsonl(args.metrics, [metrics])
    print(
        json.dumps(
            {
                "attempted": len(cases),
                "artifacts": len(results),
                "failed": sum(item["terminal_status"] == "failed" for item in results),
                "results": str(args.results),
                "events": str(args.events),
                "metrics": str(args.metrics),
                "deterministic_answer_quality": (
                    quality["status"] if quality is not None else "not_scored"
                ),
            },
            indent=2,
        )
    )
    return int(
        any(item["terminal_status"] == "failed" for item in results)
        or (quality is not None and not quality["deterministic_checks_passed"])
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, default=Path(".finai"))
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--escalation-model", default="gpt-6-luna")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--expected-cases", type=int)
    parser.add_argument("--retry-of", type=Path)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume this exact run from its completed per-case artifacts",
    )
    parser.add_argument(
        "--attempt-type", choices=("first_attempt", "retry"), default="first_attempt"
    )
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args()
    if not args.allow_live or os.environ.get("FINAI_LIVE_EVAL") != "1":
        parser.error("live execution requires --allow-live and FINAI_LIVE_EVAL=1")
    if (
        args.concurrency < 1
        or args.case_timeout_seconds <= 0
        or (args.expected_cases is not None and args.expected_cases < 1)
    ):
        parser.error("--concurrency and --case-timeout-seconds must be positive")
    try:
        return asyncio.run(execute(args))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
