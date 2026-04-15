from agents.financial.data.data_check_node import (
    _build_offline_status_from_tool_evidence,
    _merge_local_audit_status,
)
from agents.shared.utils import (
    FUNDAMENTAL_CONTEXT_FIELDS,
    FUNDAMENTAL_CORE_FIELDS,
    FUNDAMENTAL_ENRICHMENT_FIELDS,
)
from app.core.orchestration_schemas import OfflineStatus


def test_merge_local_audit_status_evaluates_ohlcv_independently() -> None:
    merged = _merge_local_audit_status(
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
    merged = _merge_local_audit_status(
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
    merged = _merge_local_audit_status(
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

    merged = _merge_local_audit_status(
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

    merged = _merge_local_audit_status(
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


def test_build_offline_status_ignores_hallucinated_submit_payload_fields() -> None:
    tool_evidence = {
        "get_ticker_info": {
            "ticker": "HDFCBANK",
            "ticker_found": True,
            "has_data": True,
            "row_count": 247,
            "latest_date": "2026-04-10T00:00:00",
        },
        "get_fundamentals_info": {
            "ticker": "HDFCBANK",
            "ticker_found": False,
            "has_data": False,
            "latest_date": None,
        },
        "get_news_info": {
            "ticker": "HDFCBANK",
            "has_data": True,
            "sql_cache": {"latest_date": "2026-04-12T15:12:14.872977"},
            "vector_db": {"has_news": False, "news_count": 0},
        },
        "get_macro_info": {
            "has_data": True,
            "latest_date": "2026-04-12T15:12:14.866657",
        },
    }
    submitted_args = {
        "data_available": True,
        "ticker_used": "HDFCBANK",
        "reasoning": "All core data types available.",
        "fundamentals_data": {
            "ticker": "HDFCBANK",
            "ticker_found": True,
            "has_data": True,
            "latest_date": "2026-04-12T15:12:14.872977",
        },
    }

    offline = _build_offline_status_from_tool_evidence(
        requested_symbol="HDFCBANK",
        submitted_args=submitted_args,
        tool_evidence=tool_evidence,
    )

    assert offline.fundamentals_data["has_data"] is False
    assert offline.fundamentals_data["ticker_found"] is False
    assert offline.data_available is False


def test_build_offline_status_marks_missing_tool_outputs_unavailable() -> None:
    offline = _build_offline_status_from_tool_evidence(
        requested_symbol="HDFCBANK",
        submitted_args={"ticker_used": "HDFCBANK", "reasoning": "done"},
        tool_evidence={
            "get_ticker_info": {
                "ticker": "HDFCBANK",
                "has_data": True,
                "row_count": 247,
            },
        },
    )

    assert offline.ohlcv_data["has_data"] is True
    assert offline.fundamentals_data["has_data"] is False
    assert offline.news_data["has_data"] is False
    assert offline.macro_data["has_data"] is False
    assert offline.data_available is False
