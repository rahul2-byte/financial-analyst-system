from evals.metrics import aggregate_metrics, evaluate_case, ndcg_at_k, reciprocal_rank


def test_retrieval_metrics_use_first_relevant_rank() -> None:
    ranked = ["x", "b", "a"]
    assert reciprocal_rank(ranked, {"a", "b"}) == 0.5
    assert ndcg_at_k(ranked, {"a", "b"}, 3) > 0.6


def test_case_metrics_require_numeric_provenance_and_relevant_citations() -> None:
    task = {
        "required_facts": [
            {"field": "debt_to_equity", "value": 0.12, "tolerance": 0.001}
        ],
        "required_risks": ["valuation", "sector"],
        "required_citations": ["filing-001"],
        "forbidden_claim_types": ["personalized_recommendation"],
        "expected_terminal_status": "validated",
    }
    result = {
        "numeric_outputs": {"debt_to_equity": 0.12},
        "risks": ["valuation", "sector"],
        "claims": [{"importance": "major", "evidence_refs": ["filing-001"]}],
        "citations": ["filing-001"],
        "terminal_status": "validated",
        "claim_types": [],
    }
    metrics = evaluate_case(task, result)
    assert metrics["numeric_provenance_rate"] == 1.0
    assert metrics["citation_precision"] == 1.0
    assert metrics["risk_f1"] == 1.0
    assert metrics["task_completed"] is True


def test_aggregate_metrics_are_zero_safe() -> None:
    metrics = aggregate_metrics([])
    assert metrics["task_completion_rate"] == 0.0
    assert metrics["case_count"] == 0
