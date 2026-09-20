"""Run approved FIN-AI cases against recorded provider replay only."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.agent_loop import AgentLoop, AgentLoopConfig, FinancialToolRunner
from app.core.agent_loop.publication import PublicationError, parse_report_draft
from app.core.resources import build_runtime_resources
from app.core.skills import SkillRegistry
from app.events.models import (
    ProviderFailed,
    RunCancelled,
    RunCompleted,
    RunFailed,
    SkillSelected,
    TextDelta,
    ToolCompleted,
    ToolFailed,
)
from app.models.request_models import Message
from app.observability.provider_archive import ProviderArchive

_HASH = re.compile(r"^[0-9a-f]{64}$")
_CASE_ID = re.compile(r"^[A-Za-z0-9_.:-]+$")
_REPLAY_KEYS = {
    "model_stream",
    "model_streams",
    "fetch_stock_price",
    "fetch_fundamentals",
    "fetch_news",
}


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError(f"{path}:{line_number}: expected a JSON object")
        cases.append(value)
    return cases


def validate_cases(cases: list[dict[str, Any]]) -> list[str]:
    errors = _validate_case_ids(cases)
    for case in cases:
        case_id = str(case.get("id") or "")
        if case.get("approved") is not True:
            errors.append(f"{case_id}: case must be approved")
        if not isinstance(case.get("query"), str) or not case["query"].strip():
            errors.append(f"{case_id}: query is required")
        for field in ("model_id", "prompt_version"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                errors.append(f"{case_id}: {field} is required")
        snapshots = case.get("replay_snapshots")
        if not isinstance(snapshots, dict):
            errors.append(f"{case_id}: replay_snapshots is required")
            snapshots = {}
        unknown = set(snapshots) - _REPLAY_KEYS
        if unknown:
            errors.append(
                f"{case_id}: unsupported replay snapshot keys: {sorted(unknown)}"
            )
        model_streams = snapshots.get("model_streams")
        if model_streams is not None:
            if not isinstance(model_streams, list) or not model_streams:
                errors.append(f"{case_id}: model_streams replay snapshots are required")
            elif any(
                not isinstance(content_hash, str) or not _HASH.fullmatch(content_hash)
                for content_hash in model_streams
            ):
                errors.append(f"{case_id}: invalid replay hash for model_streams")
        elif not _HASH.fullmatch(str(snapshots.get("model_stream") or "")):
            errors.append(f"{case_id}: model_stream replay snapshot is required")
        for operation, content_hash in snapshots.items():
            if operation == "model_streams":
                continue
            if not isinstance(content_hash, str) or not _HASH.fullmatch(content_hash):
                errors.append(f"{case_id}: invalid replay hash for {operation}")
        source_hashes = case.get("source_hashes")
        if not isinstance(source_hashes, list) or any(
            not isinstance(content_hash, str) or not _HASH.fullmatch(content_hash)
            for content_hash in source_hashes
        ):
            errors.append(f"{case_id}: source_hashes must contain SHA-256 hashes")
        if not isinstance(case.get("configuration"), dict):
            errors.append(f"{case_id}: configuration must be an object")
    return errors


def _validate_case_ids(cases: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    case_ids = [str(case.get("id") or "") for case in cases]
    if not cases:
        errors.append("at least one case is required")
    if any(not case_id for case_id in case_ids):
        errors.append("every case requires an id")
    if any(not _CASE_ID.fullmatch(case_id) for case_id in case_ids if case_id):
        errors.append("case ids must contain only safe filename characters")
    if len(set(case_ids)) != len(case_ids):
        errors.append("case ids must be unique")
    return errors


def _git_state() -> tuple[str | None, bool | None]:
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
        return revision, dirty
    except (OSError, subprocess.CalledProcessError):
        return None, None


def write_result_artifact(path: Path, payload: dict[str, Any]) -> Path:
    """Write one result without replacing an existing artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"result artifact already exists: {path}")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    try:
        os.link(temporary, path)
    except FileExistsError as exc:
        raise FileExistsError(f"result artifact already exists: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return path


async def run_offline_case(
    case: dict[str, Any],
    *,
    archive_root: Path,
    output_dir: Path,
    code_revision: str | None,
    working_tree_dirty: bool | None,
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    case_id = str(case.get("id") or "")
    run_id = str(uuid4())
    report = ""
    terminal = "failed"
    failures: list[str] = []
    observed_skills: dict[str, str] = {}
    variant_name = str(case.get("_variant") or "current")
    configuration = dict(case.get("configuration") or {})
    replay_snapshots = dict(case.get("replay_snapshots") or {})
    loop_configuration = {
        "mode": str(configuration.get("mode", "guided")),
        "max_rounds": int(configuration.get("max_rounds", 12)),
        "max_tool_calls": int(configuration.get("max_tool_calls", 24)),
        "max_tokens": int(configuration.get("max_tokens", 2048)),
        "report_max_tokens": int(configuration.get("report_max_tokens", 32768)),
        "publish_reports": bool(configuration.get("publish_reports", True)),
        "source_quality_filtering": bool(
            configuration.get("source_quality_filtering", True)
        ),
    }
    artifact: dict[str, Any] = {
        "artifact_version": "v1",
        "case_id": case_id,
        "mode": "offline_replay",
        "variant": variant_name,
        "run_id": run_id,
        "query": case.get("query", ""),
        "report": report,
        "claims": [],
        "citations": [],
        "report_validation": {"status": "pending"},
        "tool_details": [],
        "terminal_status": terminal,
        "failure_details": failures,
        "metadata": {
            "code_revision": code_revision,
            "working_tree_dirty": working_tree_dirty,
            "model_id": case.get("model_id"),
            "prompt_version": case.get("prompt_version"),
            "declared_skill_versions": case.get("declared_skill_versions", {}),
            "observed_skill_versions": observed_skills,
            "source_hashes": sorted(set(case.get("source_hashes", []))),
            "replay_snapshots": dict(sorted(replay_snapshots.items())),
            "configuration": {
                "case": configuration,
                "agent_loop": loop_configuration,
            },
            "started_at": started_at.isoformat(),
            "completed_at": None,
        },
    }
    try:
        case_errors = validate_cases([case])
        if case_errors:
            raise ValueError("; ".join(case_errors))
        resources = build_runtime_resources(
            provider_archive=ProviderArchive(archive_root),
            replay_snapshots=replay_snapshots,
            source_quality_filtering=loop_configuration["source_quality_filtering"],
        )
        loop = AgentLoop(
            resources.llm_service,
            FinancialToolRunner(resources),
            config=AgentLoopConfig(
                model=case["model_id"],
                mode=loop_configuration["mode"],
                max_rounds=loop_configuration["max_rounds"],
                max_tool_calls=loop_configuration["max_tool_calls"],
                max_tokens=loop_configuration["max_tokens"],
                report_max_tokens=loop_configuration["report_max_tokens"],
                publish_reports=loop_configuration["publish_reports"],
            ),
            skill_registry=SkillRegistry.bundled(),
        )
        async for event in loop.run(
            [Message(role="user", content=case["query"])],
            conversation_id=uuid4(),
        ):
            if isinstance(event, TextDelta):
                report += event.text
            elif isinstance(event, RunCompleted):
                terminal = event.terminal_status
            elif isinstance(event, SkillSelected):
                observed_skills[event.skill_id] = event.version
            elif isinstance(event, ToolCompleted):
                artifact["tool_details"].append(
                    {"tool": event.tool, "detail": event.detail}
                )
            elif isinstance(
                event, (RunFailed, RunCancelled, ProviderFailed, ToolFailed)
            ):
                failures.append(
                    json.dumps(event.model_dump(mode="json"), sort_keys=True)
                )
    except Exception as exc:  # noqa: BLE001 - artifact must preserve every case failure
        failures.append(f"{type(exc).__name__}: {exc}")
    completed_at = datetime.now(UTC)
    artifact["report"] = report
    try:
        draft = parse_report_draft(report)
        artifact["claims"] = [claim.model_dump(mode="json") for claim in draft.claims]
        artifact["citations"] = [
            citation.model_dump(mode="json") for citation in draft.citations
        ]
        artifact["report_validation"] = {"status": "structured"}
    except PublicationError as exc:
        artifact["report_validation"] = {
            "status": "unparsed",
            "reasons": list(exc.reasons),
        }
    artifact["terminal_status"] = terminal
    artifact["failure_details"] = failures
    artifact["metadata"]["observed_skill_versions"] = observed_skills
    artifact["metadata"]["completed_at"] = completed_at.isoformat()
    write_result_artifact(output_dir / f"{case_id}.json", artifact)
    return artifact


async def run_offline_ablations(
    cases: list[dict[str, Any]],
    *,
    archive_root: Path,
    output_dir: Path,
    code_revision: str | None,
    working_tree_dirty: bool | None,
) -> dict[str, list[dict[str, Any]]]:
    from evals.ablations import ABLATION_VARIANTS, variant_configuration

    results: dict[str, list[dict[str, Any]]] = {}
    for variant in ABLATION_VARIANTS:
        variant_results: list[dict[str, Any]] = []
        for case in cases:
            variant_case = dict(case)
            variant_case["_variant"] = variant.name
            variant_case["configuration"] = variant_configuration(
                dict(case.get("configuration") or {}), variant.name
            )
            variant_results.append(
                await run_offline_case(
                    variant_case,
                    archive_root=archive_root,
                    output_dir=output_dir / variant.name,
                    code_revision=code_revision,
                    working_tree_dirty=working_tree_dirty,
                )
            )
        results[variant.name] = variant_results
    return results


def run_offline_cases(
    cases_path: Path, *, archive_root: Path, output_dir: Path
) -> tuple[list[dict[str, Any]], int]:
    cases = load_cases(cases_path)
    errors = _validate_case_ids(cases)
    if errors:
        raise ValueError("; ".join(errors))
    revision, dirty = _git_state()
    results = asyncio.run(
        _run_cases(
            cases,
            archive_root=archive_root,
            output_dir=output_dir,
            revision=revision,
            dirty=dirty,
        )
    )
    return results, int(
        any(result["terminal_status"] == "failed" for result in results)
    )


async def _run_cases(
    cases: list[dict[str, Any]],
    *,
    archive_root: Path,
    output_dir: Path,
    revision: str | None,
    dirty: bool | None,
) -> list[dict[str, Any]]:
    return [
        await run_offline_case(
            case,
            archive_root=archive_root,
            output_dir=output_dir,
            code_revision=revision,
            working_tree_dirty=dirty,
        )
        for case in cases
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ablations", action="store_true")
    args = parser.parse_args()
    try:
        cases = load_cases(args.cases)
        case_errors = validate_cases(cases)
        if case_errors:
            raise ValueError("; ".join(case_errors))
        revision, dirty = _git_state()
        if args.ablations:
            from evals.ablations import compare_ablation_results

            grouped = asyncio.run(
                run_offline_ablations(
                    cases,
                    archive_root=args.archive_root,
                    output_dir=args.output_dir,
                    code_revision=revision,
                    working_tree_dirty=dirty,
                )
            )
            results = [item for items in grouped.values() for item in items]
            comparison = compare_ablation_results(grouped)
            write_result_artifact(args.output_dir / "ablation-summary.json", comparison)
            exit_code = int(
                any(result["terminal_status"] == "failed" for result in results)
            )
        else:
            results, exit_code = run_offline_cases(
                args.cases, archive_root=args.archive_root, output_dir=args.output_dir
            )
    except (OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    if args.ablations:
        print(json.dumps(comparison, sort_keys=True))
    for result in results:
        print(
            json.dumps(
                {
                    "case_id": result["case_id"],
                    "terminal_status": result["terminal_status"],
                    "failure_details": result["failure_details"],
                },
                sort_keys=True,
            )
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
