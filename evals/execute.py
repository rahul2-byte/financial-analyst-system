"""Execute approved benchmark cases and persist judgeable run artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import settings
from app.core.agent_loop import AgentLoop, AgentLoopConfig, FinancialToolRunner
from app.core.agent_loop.publication import PublicationError, parse_report_draft
from app.core.resources import RuntimeResources, build_runtime_resources
from app.core.skills import SkillRegistry
from app.events.models import ResearchEvent, RunCompleted, TextDelta, ToolCompleted
from app.models.request_models import Message
from app.observability.provider_archive import ProviderArchive

from evals.offline import load_cases, write_result_artifact


def result_record(artifact: dict[str, Any]) -> dict[str, Any]:
    """Return the metric-facing subset of an executed artifact."""
    return {
        "id": artifact["case_id"],
        "terminal_status": artifact["terminal_status"],
        "claims": artifact["claims"],
        "citations": artifact["citations"],
        "valid_plan": artifact["report_validation"].get("status") == "structured",
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


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


def _loop_config(case: dict[str, Any], model: str) -> AgentLoopConfig:
    configuration = case.get("configuration")
    configuration = configuration if isinstance(configuration, dict) else {}
    return AgentLoopConfig(
        model=model,
        mode=str(configuration.get("mode", "guided")),
        max_rounds=int(configuration.get("max_rounds", 12)),
        emergency_max_tool_calls=int(
            configuration.get("emergency_max_tool_calls", 128)
        ),
        max_tokens=int(configuration.get("max_tokens", 8192)),
        report_max_tokens=int(configuration.get("report_max_tokens", 32768)),
        publish_reports=bool(configuration.get("publish_reports", False)),
    )


async def execute_live_case(
    case: dict[str, Any], *, resources: RuntimeResources, model: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run one real agent trajectory and retain its complete emitted ledger."""
    case_id = str(case["case_id"])
    started = time.perf_counter()
    report = ""
    terminal_status = "failed"
    tool_calls: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    try:
        loop = AgentLoop(
            resources.llm_service,
            FinancialToolRunner(resources),
            config=_loop_config(case, model),
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
            elif event.type in {"run.failed", "run.cancelled", "provider.failed", "tool.failed"}:
                failures.append(record)
    except Exception as exc:  # noqa: BLE001 - persist every live execution failure
        failures.append({"type": type(exc).__name__, "message": str(exc)})
    claims: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    if _loop_config(case, model).publish_reports:
        validation: dict[str, Any] = {"status": "unparsed"}
        try:
            draft = parse_report_draft(report)
            claims = [claim.model_dump(mode="json") for claim in draft.claims]
            citations = [citation.model_dump(mode="json") for citation in draft.citations]
            validation = {"status": "structured"}
        except PublicationError as exc:
            validation = {"status": "unparsed", "reasons": list(exc.reasons)}
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
                "usage_permission",
                "permission_basis",
            )
        },
        "metadata": {
            "model_id": model,
            "started_at": datetime.now(UTC).isoformat(),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "event_count": len(records),
        },
    }
    return artifact, records


async def execute(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases)
    if args.limit is not None:
        cases = cases[: args.limit]
    if not cases:
        raise ValueError("no cases selected")
    archive = ProviderArchive(args.archive_root)
    if args.agent_provider == "hive":
        from app.services.hive_service import HiveService

        resources = build_runtime_resources(
            llm_service=HiveService(provider_archive=archive), provider_archive=archive
        )
    else:
        resources = build_runtime_resources(provider_archive=archive)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_records: list[dict[str, Any]] = (
        load_cases(args.events) if args.resume and args.events.exists() else []
    )
    results: list[dict[str, Any]] = []
    semaphore = asyncio.Semaphore(args.concurrency)

    async def run_case(case: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        async with semaphore:
            case_id = str(case.get("case_id") or "")
            if not case_id or not isinstance(case.get("query"), str):
                raise ValueError("each case requires case_id and query")
            target = args.output_dir / f"{case_id}.json"
            if target.exists() and args.resume:
                artifact = json.loads(target.read_text(encoding="utf-8"))
                return result_record(artifact), []
            try:
                artifact, records = await asyncio.wait_for(
                    execute_live_case(case, resources=resources, model=args.model),
                    timeout=args.case_timeout_seconds,
                )
            except TimeoutError:
                artifact = failed_artifact(
                    case, f"case timed out after {args.case_timeout_seconds} seconds"
                )
                records = []
            write_result_artifact(target, artifact)
            return result_record(artifact), records

    try:
        for task in asyncio.as_completed([asyncio.create_task(run_case(case)) for case in cases]):
            result, records = await task
            results.append(result)
            all_records.extend(records)
            _write_jsonl(args.results, results)
            _write_jsonl(args.events, all_records)
    finally:
        close = getattr(resources.llm_service, "aclose", None)
        if close is not None:
            await close()
    _write_jsonl(args.results, results)
    _write_jsonl(args.events, all_records)
    print(
        json.dumps(
            {
                "attempted": len(cases),
                "artifacts": len(results),
                "failed": sum(item["terminal_status"] == "failed" for item in results),
                "results": str(args.results),
                "events": str(args.events),
            },
            indent=2,
        )
    )
    return int(any(item["terminal_status"] == "failed" for item in results))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, default=Path(".finai"))
    parser.add_argument("--agent-provider", choices=("hive", "configured"), default="hive")
    parser.add_argument("--model", default=settings.HIVE_MODEL)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args()
    if not args.allow_live or os.environ.get("FINAI_LIVE_EVAL") != "1":
        parser.error("live execution requires --allow-live and FINAI_LIVE_EVAL=1")
    if args.concurrency < 1 or args.case_timeout_seconds <= 0:
        parser.error("--concurrency and --case-timeout-seconds must be positive")
    try:
        return asyncio.run(execute(args))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
