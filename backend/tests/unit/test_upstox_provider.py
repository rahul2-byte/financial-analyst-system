from datetime import UTC, datetime

import httpx
from data.providers.upstox import UpstoxError, UpstoxFetcher


def test_upstox_candles_are_normalized(monkeypatch) -> None:
    def fake_get(*args, **kwargs):
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "candles": [["2026-01-01T00:00:00+05:30", 10, 12, 9, 11, 100, 4]]
                },
            },
            request=httpx.Request("GET", "https://example.test"),
        )

    monkeypatch.setattr("httpx.get", fake_get)
    fetcher = UpstoxFetcher(access_token="token")
    rows = fetcher.fetch_candles(
        "NSE_EQ|INE000A00000",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert rows[0]["close"] == 11
    assert rows[0]["open_interest"] == 4


def test_upstox_requires_credentials() -> None:
    fetcher = UpstoxFetcher(access_token=None)
    try:
        fetcher.resolve_instrument("RELIANCE")
    except RuntimeError as exc:
        assert "ACCESS_TOKEN" in str(exc)
    else:
        raise AssertionError("missing credentials must fail closed")


def test_upstox_fundamentals_expose_verified_scanner_fields(monkeypatch) -> None:
    payloads = {
        "/v2/fundamentals/INE/key-ratios": {
            "data": [
                {"name": "P/E", "company_value": "20.15"},
                {"name": "P/B", "company_value": "2.13"},
                {"name": "ROE", "company_value": "8.94%"},
            ]
        },
        "/v2/fundamentals/INE/profile": {
            "data": {"sector": "Refineries", "company_profile": "Business"}
        },
    }

    def fake_get(path, params=None):
        if path in payloads:
            return {"status": "success", **payloads[path]}
        raise UpstoxError(path)

    monkeypatch.setattr(
        UpstoxFetcher, "_get", lambda self, path, params=None: fake_get(path, params)
    )
    data = UpstoxFetcher(access_token="token").fetch_fundamentals("INE")
    assert data["peRatio"] == 20.15
    assert data["priceToBook"] == 2.13
    assert data["returnOnEquity"] == 0.0894
    assert data["sector"] == "Refineries"
