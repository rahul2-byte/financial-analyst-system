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


def test_upstox_resolves_yahoo_suffix_to_exact_equity_symbol(monkeypatch) -> None:
    seen = {}

    def fake_get(self, path, params=None):
        seen.update(params)
        return {
            "status": "success",
            "data": [
                {"trading_symbol": "765HDFC34", "instrument_key": "wrong"},
                {
                    "trading_symbol": "HDFCBANK",
                    "segment": "NSE_EQ",
                    "instrument_key": "NSE_EQ|INE040A01034",
                    "isin": "INE040A01034",
                },
            ],
        }

    monkeypatch.setattr(UpstoxFetcher, "_get", fake_get)
    rows = UpstoxFetcher(access_token="token").resolve_instrument("HDFCBANK.NS")
    assert seen["query"] == "HDFCBANK"
    assert seen["exchanges"] == "NSE"
    assert seen["segments"] == "EQ"
    assert rows[0]["trading_symbol"] == "HDFCBANK"


def test_upstox_caches_normalized_instrument_resolution(monkeypatch) -> None:
    calls = 0

    def fake_get(self, path, params=None):
        nonlocal calls
        calls += 1
        return {
            "status": "success",
            "data": [{"trading_symbol": "HDFCBANK", "instrument_key": "key"}],
        }

    monkeypatch.setattr(UpstoxFetcher, "_get", fake_get)
    fetcher = UpstoxFetcher(access_token="token")
    assert fetcher.resolve_instrument("HDFCBANK.NS") == fetcher.resolve_instrument(
        "HDFCBANK"
    )
    assert calls == 1


def test_upstox_quota_exhaustion_is_a_handled_provider_error(monkeypatch) -> None:
    def exhausted(provider):
        from app.core.quota import QuotaExceeded

        raise QuotaExceeded(provider)

    fetcher = UpstoxFetcher(access_token="token")
    monkeypatch.setattr(fetcher.quota, "reserve", exhausted)
    try:
        fetcher.resolve_instrument("HDFCBANK.NS")
    except UpstoxError as exc:
        assert "budget exhausted" in str(exc)
    else:
        raise AssertionError("quota exhaustion must become an UpstoxError")


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


def test_upstox_market_status_normalizes_exchange_state(monkeypatch) -> None:
    def fake_get(self, path, params=None):
        assert path == "/v2/market/status/NSE"
        assert params is None
        return {
            "status": "success",
            "data": {
                "exchange": "NSE",
                "status": "NORMAL_OPEN",
                "last_updated": 1705549500000,
            },
        }

    monkeypatch.setattr(UpstoxFetcher, "_get", fake_get)
    result = UpstoxFetcher(access_token="token").fetch_market_status("NSE")
    assert result == {
        "exchange": "NSE",
        "status": "NORMAL_OPEN",
        "last_updated": 1705549500000,
    }


def test_upstox_market_holidays_accepts_date_filter(monkeypatch) -> None:
    def fake_get(self, path, params=None):
        assert path == "/v2/market/holidays"
        assert params == {"date": "2026-01-26"}
        return {
            "status": "success",
            "data": [{"date": "2026-01-26", "holiday_type": "TRADING_HOLIDAY"}],
        }

    monkeypatch.setattr(UpstoxFetcher, "_get", fake_get)
    result = UpstoxFetcher(access_token="token").fetch_market_holidays("2026-01-26")
    assert result[0]["holiday_type"] == "TRADING_HOLIDAY"
