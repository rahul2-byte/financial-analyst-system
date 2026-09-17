from evals.labels import validate_human_labels


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
