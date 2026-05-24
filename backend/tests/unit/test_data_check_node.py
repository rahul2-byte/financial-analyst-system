from agents.financial.data.status_merge import merge_local_audit_status
from agents.shared.utils import (
    FUNDAMENTAL_CONTEXT_FIELDS,
    FUNDAMENTAL_CORE_FIELDS,
    FUNDAMENTAL_ENRICHMENT_FIELDS,
)
from app.core.orchestration_schemas import OfflineStatus


def test_merge_local_audit_status_evaluates_ohlcv_independently() -> None:
    merged = merge_local_audit_status(
        {},
        "AAPL",
        OfflineStatus(
            data_available=False,
            ticker_used="AAPL",
            reasoning="Missing news.",
            ohlcv_data={
                "has_data": True,
                "latest_date": "2026-04-08",
                "row_count": 126,
            },
            macro_data={"has_data": False},
        ),
        {"ohlcv": {"expected_points": 1260}},
    )

    assert merged["ohlcv"]["by_symbol"]["AAPL"]["available"] is True
    assert merged["ohlcv"]["by_symbol"]["AAPL"]["error"] is None


def test_merge_local_audit_status_parses_nested_json() -> None:
    merged = merge_local_audit_status(
        {},
        "AAPL",
        OfflineStatus(
            data_available=True,
            ticker_used="AAPL",
            reasoning="ok",
            ohlcv_data={"latest_date": "2026-04-08", "row_count": 126},
            macro_data={"has_data": True, "latest_date": "2026-04-08"},
        ),
        {"ohlcv": {"expected_points": 1260}},
    )

    assert merged["ohlcv"]["coverage"] == 0.1
    assert merged["macro"]["available"] is True


def test_merge_local_audit_status_does_not_copy_ohlcv_coverage_to_fundamentals() -> (
    None
):
    merged = merge_local_audit_status(
        {},
        "AAPL",
        OfflineStatus(
            data_available=True,
            ticker_used="AAPL",
            reasoning="ok",
            ohlcv_data={"latest_date": "2026-04-08", "row_count": 126},
        ),
        {
            "ohlcv": {"expected_points": 1260},
            "fundamentals": {"required_fields": ["marketCap", "currentPrice"]},
        },
    )

    assert merged["ohlcv"]["coverage"] == 0.1
    assert merged["fundamentals"]["coverage"] == 0.0


def test_merge_local_audit_status_uses_canonical_fundamentals_when_policy_empty() -> (
    None
):
    fundamentals_data = {field: 1.0 for field in FUNDAMENTAL_CORE_FIELDS}
    fundamentals_data["has_data"] = True

    merged = merge_local_audit_status(
        {},
        "AAPL",
        OfflineStatus(
            data_available=True,
            ticker_used="AAPL",
            reasoning="ok",
            fundamentals_data=fundamentals_data,
        ),
        {"fundamentals": {}},
    )

    assert merged["fundamentals"]["by_symbol"]["AAPL"]["available"] is True
    assert merged["fundamentals"]["by_symbol"]["AAPL"]["coverage"] == 0.7


def test_merge_local_audit_status_uses_full_fundamental_payload_schema() -> None:
    fundamentals_data = {field: 1.0 for field in FUNDAMENTAL_CORE_FIELDS}
    fundamentals_data.update({field: "x" for field in FUNDAMENTAL_CONTEXT_FIELDS})
    fundamentals_data.update({field: 1.0 for field in FUNDAMENTAL_ENRICHMENT_FIELDS})
    fundamentals_data["has_data"] = True

    merged = merge_local_audit_status(
        {},
        "AAPL",
        OfflineStatus(
            data_available=True,
            ticker_used="AAPL",
            reasoning="ok",
            fundamentals_data=fundamentals_data,
        ),
        {"fundamentals": {}},
    )

    assert merged["fundamentals"]["by_symbol"]["AAPL"]["coverage"] == 1.0
