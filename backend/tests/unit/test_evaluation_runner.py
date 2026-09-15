import json
from argparse import Namespace

from evals.run import run


def test_runner_marks_incomplete_gold_set_as_insufficient(tmp_path) -> None:
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text(json.dumps({"id": "case-1"}) + "\n", encoding="utf-8")
    results = tmp_path / "results.jsonl"
    results.write_text("", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    output = run(
        Namespace(
            mode="offline",
            tasks=str(tasks),
            results=str(results),
            manifest=str(manifest),
            model_id="test-model",
            prompt_version="test-prompt",
            configuration_hash="test-config",
            random_seed=7,
            expected_cases=100,
        )
    )

    assert output["status"] == "insufficient_evidence"
    assert output["missing_results"] == ["case-1"]
    assert output["metadata"]["random_seed"] == 7
