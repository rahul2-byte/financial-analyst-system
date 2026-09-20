import json

from evals.benchmark import classify_benchmark_artifacts, validate_benchmark_artifacts


def test_benchmark_artifacts_require_exact_result_ids(tmp_path) -> None:
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text('{"id":"a"}\n', encoding="utf-8")
    results = tmp_path / "results.jsonl"
    results.write_text('{"id":"b"}\n', encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"version": "v1", "status": "seeded_fixture"}), encoding="utf-8"
    )

    errors = validate_benchmark_artifacts(tasks, results, manifest, expected_cases=1)

    assert "results must match task ids exactly" in errors


def test_seeded_fixture_is_contract_only_even_when_complete(tmp_path) -> None:
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text('{"id":"a"}\n', encoding="utf-8")
    results = tmp_path / "results.jsonl"
    results.write_text('{"id":"a"}\n', encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"version": "v1", "status": "seeded_fixture"}),
        encoding="utf-8",
    )

    assert (
        classify_benchmark_artifacts(tasks, results, manifest, 1)
        == "synthetic_contract"
    )


def test_market_quality_requires_source_provenance(tmp_path) -> None:
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text('{"id":"a"}\n', encoding="utf-8")
    results = tmp_path / "results.jsonl"
    results.write_text('{"id":"a"}\n', encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "v1",
                "status": "frozen_public",
                "sources": [{"id": "source-1"}],
            }
        ),
        encoding="utf-8",
    )

    assert (
        classify_benchmark_artifacts(tasks, results, manifest, 1)
        == "insufficient_evidence"
    )


def test_complete_provenance_backed_artifacts_are_market_quality(tmp_path) -> None:
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text('{"id":"a"}\n', encoding="utf-8")
    results = tmp_path / "results.jsonl"
    results.write_text('{"id":"a"}\n', encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "v1",
                "status": "frozen_public",
                "sources": [
                    {
                        "id": "source-1",
                        "sha256": "abc",
                        "retrieved_at": "2026-09-19T00:00:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert (
        classify_benchmark_artifacts(tasks, results, manifest, 1)
        == "market_quality_measured"
    )
