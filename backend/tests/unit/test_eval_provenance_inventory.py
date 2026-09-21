from evals.provenance_inventory import _case


def test_case_query_uses_the_snapshot_ticker() -> None:
    case = _case(
        {
            "snapshot_id": "a" * 64,
            "data_type": "fetch_stock_price",
            "ticker": "TCS.NS",
            "source_url": "https://api.upstox.com",
            "retrieved_at": "2026-09-21T00:00:00Z",
            "content_sha256": "b" * 64,
            "usage_permission": "private_evaluation_authorized",
            "permission_basis": "owner authorization",
        },
        1,
        "price",
        "What closing price is available for {ticker}?",
    )

    assert "TCS.NS" in case["query"]
