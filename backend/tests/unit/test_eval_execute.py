from evals.execute import _loop_config, _write_jsonl, failed_artifact, result_record


def test_result_record_preserves_case_identity_and_structured_output() -> None:
    artifact = {
        "case_id": "real-v1-001",
        "terminal_status": "completed_with_limited_evidence",
        "claims": [{"claim_id": "claim-1"}],
        "citations": [{"citation_id": "citation-1"}],
        "report_validation": {"status": "structured"},
    }

    assert result_record(artifact) == {
        "id": "real-v1-001",
        "terminal_status": "completed_with_limited_evidence",
        "claims": [{"claim_id": "claim-1"}],
        "citations": [{"citation_id": "citation-1"}],
        "valid_plan": True,
    }


def test_failed_artifact_is_judgeable() -> None:
    artifact = failed_artifact({"case_id": "real-v1-002", "query": "Q"}, "timeout")

    assert artifact["terminal_status"] == "failed"
    assert artifact["failure_details"][0]["message"] == "timeout"
    assert result_record(artifact)["id"] == "real-v1-002"


def test_live_executor_uses_the_runtime_model_token_default() -> None:
    config = _loop_config({}, "test-model")

    assert config.max_tokens == 8192
    assert config.publish_reports is False


def test_checkpoint_writer_persists_completed_rows(tmp_path) -> None:
    target = tmp_path / "results.jsonl"

    _write_jsonl(target, [{"id": "case-1"}])

    assert target.read_text(encoding="utf-8") == '{"id": "case-1"}\n'
