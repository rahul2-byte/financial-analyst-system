from app.core.orchestration_schemas import OfflineStatus


def test_merge_local_audit_status_preserves_existing_symbol_entries() -> None:
    from agents.financial.data.status_merge import merge_local_audit_status

    existing = {
        "ohlcv": {
            "by_symbol": {
                "MSFT": {
                    "available": True,
                    "freshness": 0.9,
                    "coverage": 0.8,
                    "source": "db_check",
                    "error": None,
                }
            }
        }
    }
    offline = OfflineStatus(
        data_available=True,
        ticker_used="AAPL",
        reasoning="ok",
        ohlcv_data={"has_data": True, "latest_date": "2026-04-10", "row_count": 252},
        fundamentals_data={"has_data": True, "marketCap": 1},
        news_data={
            "has_data": True,
            "sql_cache": {"latest_date": "2026-04-10"},
            "vector_db": {"has_news": True},
        },
        macro_data={"has_data": True, "latest_date": "2026-04-10"},
    )

    merged = merge_local_audit_status(existing, "AAPL", offline, {"ohlcv": {"expected_points": 252}})

    assert "MSFT" in merged["ohlcv"]["by_symbol"]
    assert "AAPL" in merged["ohlcv"]["by_symbol"]
    assert merged["ohlcv"]["available"] is True
