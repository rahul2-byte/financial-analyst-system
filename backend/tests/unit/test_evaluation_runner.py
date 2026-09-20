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


def test_runner_cannot_upgrade_ten_case_seeded_fixture_to_market_quality(
    tmp_path,
) -> None:
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text("".join(json.dumps({"id": f"case-{i}"}) + "\n" for i in range(10)))
    results = tmp_path / "results.jsonl"
    results.write_text(
        "".join(json.dumps({"id": f"case-{i}"}) + "\n" for i in range(10))
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"version": "v1", "status": "seeded_fixture"}),
        encoding="utf-8",
    )

    args = Namespace(
        mode="offline",
        tasks=str(tasks),
        results=str(results),
        manifest=str(manifest),
        model_id="test-model",
        prompt_version="test-prompt",
        configuration_hash="test-config",
        random_seed=7,
        expected_cases=10,
    )
    assert run(args)["status"] == "synthetic_contract"
    args.expected_cases = 100
    assert run(args)["status"] == "insufficient_evidence"


def test_runner_reports_human_claim_support_and_judge_disagreement(tmp_path) -> None:
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text(json.dumps({"id": "case-1"}) + "\n", encoding="utf-8")
    results = tmp_path / "results.jsonl"
    results.write_text(
        json.dumps(
            {
                "id": "case-1",
                "terminal_status": "success",
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "text": "Claim",
                        "importance": "major",
                        "evidence_refs": ["citation-1"],
                        "numeric_refs": [],
                    }
                ],
                "citations": [{"citation_id": "citation-1", "source_id": "source-1"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"version": "v1", "status": "seeded_fixture"}),
        encoding="utf-8",
    )
    labels = tmp_path / "labels.jsonl"
    labels.write_text(
        "".join(
            json.dumps(
                {
                    "case_id": "case-1",
                    "claim_id": "claim-1",
                    "labeler_id": labeler,
                    "source_id": "source-1",
                    "evidence_span": "span",
                    "numeric_value_correct": None,
                    "semantic_judgment": "supports",
                }
            )
            + "\n"
            for labeler in ("a", "b")
        ),
        encoding="utf-8",
    )
    judges = tmp_path / "judges.jsonl"
    judges.write_text(
        json.dumps(
            {
                "case_id": "case-1",
                "claim_id": "claim-1",
                "semantic_judgment": "unsupported",
                "numeric_value_correct": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )

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
            expected_cases=1,
            human_labels=str(labels),
            judge_results=str(judges),
        )
    )

    support = output["metrics"]["human_claim_support"]
    assert support["source_supports_claim"] == {"count": 1, "denominator": 1}
    assert support["judge_comparison"]["semantic_disagreement"] == {
        "count": 1,
        "denominator": 1,
    }
    assert output["label_validation_errors"] == []
