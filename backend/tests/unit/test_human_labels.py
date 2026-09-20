from evals.labels import validate_claim_support_labels, validate_human_labels


def test_labels_require_two_independent_labelers() -> None:
    errors = validate_human_labels(
        [
            {
                "item_id": "c1",
                "labeler_id": "a",
                "evidence_span": "p1",
                "judgment": "correct",
            }
        ]
    )
    assert "two independent labelers" in errors[0]


def test_disagreement_requires_adjudication() -> None:
    errors = validate_human_labels(
        [
            {
                "item_id": "c1",
                "labeler_id": "a",
                "evidence_span": "p1",
                "judgment": "correct",
            },
            {
                "item_id": "c1",
                "labeler_id": "b",
                "evidence_span": "p1",
                "judgment": "incorrect",
            },
        ]
    )
    assert "adjudication" in errors[0]


def test_claim_support_labels_require_structured_fields() -> None:
    labels = [
        {
            "case_id": "case-1",
            "claim_id": "claim-1",
            "labeler_id": "a",
            "source_id": "source-1",
            "evidence_span": "source span",
            "numeric_value_correct": True,
            "semantic_judgment": "supports",
        },
        {
            "case_id": "case-1",
            "claim_id": "claim-1",
            "labeler_id": "b",
            "source_id": "source-1",
            "evidence_span": "source span",
            "numeric_value_correct": True,
            "semantic_judgment": "supports",
        },
    ]

    assert validate_claim_support_labels(labels) == []


def test_claim_support_labels_reject_invalid_judgment() -> None:
    errors = validate_claim_support_labels(
        [
            {
                "case_id": "case-1",
                "claim_id": "claim-1",
                "labeler_id": "a",
                "source_id": "source-1",
                "evidence_span": "source span",
                "numeric_value_correct": None,
                "semantic_judgment": "maybe",
            }
        ]
    )

    assert "semantic_judgment" in " ".join(errors)
