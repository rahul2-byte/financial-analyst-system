import json
from collections import Counter
from pathlib import Path

from evals.labels import validate_candidate_cases
from evals.snapshots import validate_candidate_source_record


def test_candidate_source_metadata_must_be_pending() -> None:
    errors = validate_candidate_source_record(
        {"status": "candidate", "source_url": "https://example.test"}
    )

    assert "candidate source must remain unresolved" in errors


def test_candidate_source_metadata_fields_are_explicit() -> None:
    errors = validate_candidate_source_record(
        {"status": "pending_owner_source", "source_url": None}
    )

    assert "candidate source requires publisher" in errors


def test_candidate_cases_require_unique_ids() -> None:
    cases = [{"id": "case-1"}, {"id": "case-1"}]

    errors = validate_candidate_cases(cases, expected_cases=2)

    assert "case ids must be unique" in errors


def test_candidate_cases_require_review_fields() -> None:
    errors = validate_candidate_cases(
        [{"id": "case-1", "category": "fundamentals"}], expected_cases=1
    )

    joined = " ".join(errors)
    assert "expected_evidence" in joined
    assert "labeling_instructions" in joined


def test_pilot_candidate_manifest_has_balanced_categories() -> None:
    path = Path("evals/candidates/pilot-v1/cases.jsonl")
    cases = [json.loads(line) for line in path.read_text().splitlines()]

    assert validate_candidate_cases(cases) == []
    assert Counter(case["category"] for case in cases) == {
        "fundamentals": 4,
        "technical": 4,
        "news_source": 4,
        "conflicting_evidence": 4,
        "insufficient_evidence": 4,
    }
