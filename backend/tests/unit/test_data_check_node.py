from agents.financial.data.data_check_node import _merge_local_audit_status
from app.core.orchestration_schemas import OfflineStatus


def test_merge_local_audit_status_uses_timeframe_expected_points() -> None:
    merged = _merge_local_audit_status(
        {},
        "AAPL",
        OfflineStatus(
            data_available=True,
            ticker_used="AAPL",
            reasoning="ok",
            extra_info={"latest_date": "2026-04-08", "row_count": 126},
        ),
        {"ohlcv": {"expected_points": 1260}},
    )

    assert merged["ohlcv"]["coverage"] == 0.1


def test_merge_local_audit_status_does_not_copy_ohlcv_coverage_to_fundamentals() -> None:
    merged = _merge_local_audit_status(
        {},
        "AAPL",
        OfflineStatus(
            data_available=True,
            ticker_used="AAPL",
            reasoning="ok",
            extra_info={"latest_date": "2026-04-08", "row_count": 126},
        ),
        {
            "ohlcv": {"expected_points": 1260},
            "fundamentals": {"required_fields": ["marketCap", "currentPrice"]},
        },
    )

    assert merged["ohlcv"]["coverage"] == 0.1
    assert merged["fundamentals"]["coverage"] == 0.0
