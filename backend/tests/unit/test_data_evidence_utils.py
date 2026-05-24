from agents.financial.data.evidence_utils import (
    as_dict_or_empty,
    normalize_dataset_evidence,
)


def test_as_dict_or_empty_returns_dict_or_empty() -> None:
    assert as_dict_or_empty({"has_data": True}) == {"has_data": True}
    assert as_dict_or_empty(None) == {}
    assert as_dict_or_empty("bad") == {}


def test_normalize_dataset_evidence_marks_missing_with_ticker() -> None:
    normalized = normalize_dataset_evidence(None, ticker="AAPL")

    assert normalized["has_data"] is False
    assert normalized["ticker"] == "AAPL"
    assert normalized["error"] == "LOCAL_DATA_MISSING"


def test_normalize_dataset_evidence_preserves_existing_error_and_fields() -> None:
    normalized = normalize_dataset_evidence(
        {"has_data": False, "error": "NEWS_STALE", "row_count": 0},
        ticker="AAPL",
    )

    assert normalized["has_data"] is False
    assert normalized["error"] == "NEWS_STALE"
    assert normalized["row_count"] == 0
