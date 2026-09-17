import json

from evals.benchmark import validate_benchmark_artifacts


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
