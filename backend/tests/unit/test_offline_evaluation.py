import asyncio
import json
from datetime import UTC, datetime

import pytest
from app.observability.provider_archive import ProviderArchive, ProviderSnapshot

from evals.offline import (
    run_offline_ablations,
    run_offline_case,
    run_offline_cases,
    validate_cases,
    write_result_artifact,
)


def _case(model_hash: str | None) -> dict:
    return {
        "id": "case-001",
        "approved": True,
        "query": "Replay this approved case.",
        "model_id": "replay-model",
        "prompt_version": "prompt-v1",
        "declared_skill_versions": {},
        "source_hashes": ["a" * 64],
        "replay_snapshots": {"model_stream": model_hash},
        "configuration": {"mode": "guided", "publish_reports": False},
    }


def _model_snapshot(tmp_path):
    archive = ProviderArchive(tmp_path)
    return archive.store(
        ProviderSnapshot(
            provider="hive",
            operation="model_stream",
            payload=[{"event": "token", "data": "replayed report"}],
            fetched_at=datetime(2026, 9, 18, tzinfo=UTC),
        )
    )


def _structured_report_snapshot(tmp_path):
    report = {
        "executive_summary": "A summary.",
        "key_drivers": ["A driver."],
        "detailed_analysis": "Detailed analysis.",
        "risks": ["A risk."],
        "final_view": "A view.",
        "claims": [
            {
                "claim_id": "claim-1",
                "text": "A claim.",
                "importance": "major",
                "evidence_refs": ["citation-1"],
                "numeric_refs": [],
            }
        ],
        "citations": [{"citation_id": "citation-1", "source_id": "source-1"}],
    }
    archive = ProviderArchive(tmp_path)
    return archive.store(
        ProviderSnapshot(
            provider="hive",
            operation="model_stream",
            payload=[{"event": "token", "data": json.dumps(report)}],
            fetched_at=datetime(2026, 9, 18, tzinfo=UTC),
        )
    )


def test_offline_case_writes_report_and_terminal_status(tmp_path) -> None:
    snapshot = _model_snapshot(tmp_path)

    result = asyncio.run(
        run_offline_case(
            _case(snapshot.content_hash),
            archive_root=tmp_path,
            output_dir=tmp_path / "results",
            code_revision="abc123",
            working_tree_dirty=False,
        )
    )

    assert result["report"] == "replayed report"
    assert result["terminal_status"]
    assert result["metadata"]["model_id"] == "replay-model"
    assert result["metadata"]["prompt_version"] == "prompt-v1"
    assert result["metadata"]["replay_snapshots"]["model_stream"] == (
        snapshot.content_hash
    )
    assert (tmp_path / "results" / "case-001.json").is_file()


def test_offline_case_persists_structured_claims_and_citations(tmp_path) -> None:
    snapshot = _structured_report_snapshot(tmp_path)

    result = asyncio.run(
        run_offline_case(
            _case(snapshot.content_hash),
            archive_root=tmp_path,
            output_dir=tmp_path / "results",
            code_revision="abc123",
            working_tree_dirty=False,
        )
    )

    assert result["claims"][0]["claim_id"] == "claim-1"
    assert result["citations"][0]["source_id"] == "source-1"


def test_offline_ablations_write_all_four_paired_variants(tmp_path) -> None:
    snapshot = _model_snapshot(tmp_path)

    results = asyncio.run(
        run_offline_ablations(
            [_case(snapshot.content_hash)],
            archive_root=tmp_path,
            output_dir=tmp_path / "ablations",
            code_revision="abc123",
            working_tree_dirty=False,
        )
    )

    assert set(results) == {
        "baseline",
        "quality_only",
        "publication_only",
        "full",
    }
    assert all(len(items) == 1 for items in results.values())
    assert all(
        (tmp_path / "ablations" / variant / "case-001.json").is_file()
        for variant in results
    )
    assert results["baseline"][0]["variant"] == "baseline"
    assert (
        results["baseline"][0]["metadata"]["configuration"]["agent_loop"][
            "publish_reports"
        ]
        is False
    )
    assert (
        results["full"][0]["metadata"]["configuration"]["agent_loop"]["publish_reports"]
        is True
    )


def test_offline_case_requires_model_replay(tmp_path) -> None:
    result = asyncio.run(
        run_offline_case(
            _case(None),
            archive_root=tmp_path,
            output_dir=tmp_path / "results",
            code_revision="abc123",
            working_tree_dirty=False,
        )
    )

    assert result["terminal_status"] == "failed"
    assert "model_stream" in result["failure_details"][0]


def test_offline_case_writes_failure_artifact(tmp_path) -> None:
    missing_hash = "0" * 64
    result = asyncio.run(
        run_offline_case(
            _case(missing_hash),
            archive_root=tmp_path,
            output_dir=tmp_path / "results",
            code_revision="abc123",
            working_tree_dirty=False,
        )
    )

    assert result["terminal_status"] == "failed"
    assert "snapshot unavailable" in result["failure_details"][0]
    artifact = json.loads(
        (tmp_path / "results" / "case-001.json").read_text(encoding="utf-8")
    )
    assert artifact["terminal_status"] == "failed"


def test_result_artifact_is_immutable(tmp_path) -> None:
    path = tmp_path / "case.json"
    payload = {"case_id": "case-001", "terminal_status": "success"}
    write_result_artifact(path, payload)

    with pytest.raises(FileExistsError):
        write_result_artifact(path, {"case_id": "case-001"})

    assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_offline_case_manifest_rejects_missing_or_duplicate_ids() -> None:
    missing = _case("0" * 64)
    missing.pop("id")
    assert "every case requires an id" in validate_cases([missing])

    duplicate = _case("0" * 64)
    duplicate["id"] = "case-001"
    errors = validate_cases([duplicate, duplicate])

    assert "case ids must be unique" in errors


def test_offline_case_manifest_accepts_ordered_model_streams() -> None:
    case = _case(None)
    case["replay_snapshots"] = {"model_streams": ["a" * 64, "b" * 64]}

    assert validate_cases([case]) == []


def test_offline_case_manifest_rejects_empty_ordered_model_streams() -> None:
    case = _case(None)
    case["replay_snapshots"] = {"model_streams": []}

    assert any("model_streams" in error for error in validate_cases([case]))


def test_batch_writes_failed_artifact_for_missing_replay(tmp_path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(json.dumps(_case(None)) + "\n", encoding="utf-8")

    results, exit_code = run_offline_cases(
        cases_path,
        archive_root=tmp_path,
        output_dir=tmp_path / "results",
    )

    assert exit_code == 1
    assert results[0]["terminal_status"] == "failed"
    assert (tmp_path / "results" / "case-001.json").is_file()
