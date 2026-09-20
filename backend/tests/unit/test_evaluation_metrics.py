from evals.metrics import (
    aggregate_metrics,
    evaluate_case,
    evaluate_claim_support,
    hit_rate_at_k,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)


def _claim_labels() -> list[dict]:
    labels = []
    judgments = {
        "claim-1": (True, "supports"),
        "claim-2": (None, "contradicts"),
        "claim-3": (None, "unsupported"),
    }
    for claim_id, (numeric, judgment) in judgments.items():
        for labeler_id in ("a", "b"):
            labels.append(
                {
                    "case_id": "case-1",
                    "claim_id": claim_id,
                    "labeler_id": labeler_id,
                    "source_id": f"source-{claim_id}",
                    "evidence_span": f"span for {claim_id}",
                    "numeric_value_correct": numeric,
                    "semantic_judgment": judgment,
                }
            )
    return labels


def test_retrieval_metrics_use_first_relevant_rank() -> None:
    ranked = ["x", "b", "a"]
    assert reciprocal_rank(ranked, {"a", "b"}) == 0.5
    assert ndcg_at_k(ranked, {"a", "b"}, 3) > 0.6


def test_retrieval_metrics_keep_hit_rate_separate_from_recall() -> None:
    ranked = ["a", "x"]
    relevant = {"a", "b"}
    assert hit_rate_at_k(ranked, relevant, 2) == 1.0
    assert recall_at_k(ranked, relevant, 2) == 0.5
    assert recall_at_k(ranked, set(), 2) == 0.0


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


def test_empty_metric_denominators_are_explicitly_zero_safe() -> None:
    task = {
        "required_facts": [],
        "required_citations": [],
        "required_risks": [],
        "expected_terminal_status": "success",
    }
    result = {"terminal_status": "success", "claims": [], "citations": []}
    metrics = evaluate_case(task, result)
    assert metrics["major_claim_support_rate"] == 0.0
    assert metrics["citation_precision"] == 0.0
    assert metrics["citation_recall"] == 0.0
    assert metrics["risk_f1"] == 1.0
    assert metrics["abstention_expected"] is False
    assert metrics["abstention_correct"] is False
    assert aggregate_metrics([metrics])["abstention_accuracy"] == 0.0


def test_citations_without_required_citations_have_no_supported_denominator() -> None:
    metrics = evaluate_case(
        {"required_citations": [], "expected_terminal_status": "success"},
        {"citations": ["unverified"], "terminal_status": "success"},
    )
    assert metrics["citation_precision"] == 0.0
    assert metrics["citation_recall"] == 0.0


def test_claim_support_reports_counts_denominators_and_failures() -> None:
    result = {
        "claims": [
            {
                "claim_id": "claim-1",
                "text": "Numeric claim",
                "importance": "major",
                "evidence_refs": ["citation-1"],
                "numeric_refs": ["fact-1"],
            },
            {
                "claim_id": "claim-2",
                "text": "Contradicted claim",
                "importance": "major",
                "evidence_refs": ["citation-2"],
                "numeric_refs": [],
            },
            {
                "claim_id": "claim-3",
                "text": "Unsupported claim",
                "importance": "major",
                "evidence_refs": ["missing-citation"],
                "numeric_refs": [],
            },
        ],
        "citations": [
            {"citation_id": "citation-1", "source_id": "source-claim-1"},
            {"citation_id": "citation-2", "source_id": "source-claim-2"},
        ],
    }

    metrics = evaluate_claim_support("case-1", result, _claim_labels())

    assert metrics["major_claims"] == {"count": 3, "denominator": 3}
    assert metrics["valid_reference"] == {"count": 2, "denominator": 3}
    assert metrics["numeric_value_correct"] == {"count": 1, "denominator": 1}
    assert metrics["source_supports_claim"] == {"count": 1, "denominator": 3}
    assert metrics["contradictory_source_evidence"] == {"count": 1, "denominator": 3}
    assert metrics["unsupported_conclusion"] == {"count": 1, "denominator": 3}
    assert metrics["failure_examples"]


def test_claim_support_reports_judge_disagreement_separately() -> None:
    result = {
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
    labels = [
        {
            "case_id": "case-1",
            "claim_id": "claim-1",
            "labeler_id": labeler,
            "source_id": "source-1",
            "evidence_span": "span",
            "numeric_value_correct": None,
            "semantic_judgment": "supports",
        }
        for labeler in ("a", "b")
    ]
    judge = [
        {
            "case_id": "case-1",
            "claim_id": "claim-1",
            "numeric_value_correct": None,
            "semantic_judgment": "unsupported",
        }
    ]

    metrics = evaluate_claim_support("case-1", result, labels, judge)

    assert metrics["judge_comparison"]["semantic_disagreement"] == {
        "count": 1,
        "denominator": 1,
    }
    assert metrics["source_supports_claim"] == {"count": 1, "denominator": 1}
