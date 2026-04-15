from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock

from data.schemas.market import OHLCVData
from storage.sql.client import PostgresClient


def test_save_ohlcv_avoids_prefetching_existing_dates_before_insert():
    client = PostgresClient.__new__(PostgresClient)
    mock_session = MagicMock()

    @contextmanager
    def fake_session():
        yield mock_session

    client.get_session = fake_session  # type: ignore[method-assign]

    rows = [
        OHLCVData(
            ticker="AAPL",
            date="2025-01-02",
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0,
            volume=1000,
            adjusted_close=103.0,
        )
    ]

    client.save_ohlcv(rows)

    assert mock_session.exec.call_count == 0
    assert mock_session.execute.call_count == 1


def test_get_fundamentals_info_falls_back_to_yahoo_suffix_variants():
    client = PostgresClient.__new__(PostgresClient)
    mock_session = MagicMock()

    class _Result:
        def __init__(self, value):
            self._value = value

        def first(self):
            return self._value

    calls = []

    def execute(statement, params):
        calls.append(params["ticker"])
        if params["ticker"] == "HDFCBANK":
            return _Result(None)
        if params["ticker"] == "HDFCBANK.NS":
            return _Result(
                {
                    "ticker": "HDFCBANK",
                    "updated_at": datetime(2026, 4, 12, 18, 39, 46, 667365),
                    "name": "HDFC BANK LTD",
                    "industry": "Banks",
                    "sector": "Financial Services",
                    "market_cap": 1_000_000,
                    "pe_ratio": 19.2,
                    "forward_pe": 17.5,
                    "peg_ratio": 1.3,
                    "price_to_book": 2.7,
                    "debt_to_equity": 0.9,
                    "return_on_equity": 0.18,
                    "profit_margins": 0.22,
                    "revenue_growth": 0.14,
                    "earnings_growth": 0.11,
                    "dividend_yield": 0.01,
                    "current_price": 1640.5,
                    "target_mean_price": 1725.0,
                    "fifty_two_week_high": 1794.0,
                    "fifty_two_week_low": 1363.55,
                }
            )
        return _Result(None)

    mock_session.execute.side_effect = execute

    @contextmanager
    def fake_session():
        yield mock_session

    client.get_session = fake_session  # type: ignore[method-assign]

    result = client.get_fundamentals_info("HDFCBANK")

    assert calls == ["HDFCBANK", "HDFCBANK.NS"]
    assert result["ticker"] == "HDFCBANK"
    assert result["ticker_found"] is True
    assert result["has_data"] is True
    assert result["updated_at"] == "2026-04-12T18:39:46.667365"
    assert result["latest_date"] == "2026-04-12T18:39:46.667365"
    assert result["marketCap"] == 1_000_000
    assert result["priceToBook"] == 2.7
    assert result["returnOnEquity"] == 0.18
    assert result["debtToEquity"] == 0.9


def test_get_fundamentals_info_returns_full_snapshot_shape():
    client = PostgresClient.__new__(PostgresClient)
    mock_session = MagicMock()

    class _Result:
        def __init__(self, value):
            self._value = value

        def first(self):
            return self._value

    updated_at = datetime(2026, 4, 13, 9, 15, 30, 123456)

    def execute(statement, params):
        assert params["ticker"] == "HDFCBANK"
        return _Result(
            {
                "ticker": "HDFCBANK",
                "updated_at": updated_at,
                "name": "HDFC BANK LTD",
                "industry": "Banks",
                "sector": "Financial Services",
                "market_cap": 1_000_000,
                "pe_ratio": 19.2,
                "forward_pe": 17.5,
                "peg_ratio": 1.3,
                "price_to_book": 2.7,
                "debt_to_equity": 0.9,
                "return_on_equity": 0.18,
                "profit_margins": 0.22,
                "revenue_growth": 0.14,
                "earnings_growth": 0.11,
                "dividend_yield": 0.01,
                "current_price": 1640.5,
                "target_mean_price": 1725.0,
                "fifty_two_week_high": 1794.0,
                "fifty_two_week_low": 1363.55,
            }
        )

    mock_session.execute.side_effect = execute

    @contextmanager
    def fake_session():
        yield mock_session

    client.get_session = fake_session  # type: ignore[method-assign]

    result = client.get_fundamentals_info("HDFCBANK")

    assert result == {
        "ticker": "HDFCBANK",
        "ticker_found": True,
        "has_data": True,
        "updated_at": "2026-04-13T09:15:30.123456",
        "latest_date": "2026-04-13T09:15:30.123456",
        "name": "HDFC BANK LTD",
        "industry": "Banks",
        "sector": "Financial Services",
        "marketCap": 1_000_000,
        "peRatio": 19.2,
        "forwardPE": 17.5,
        "pegRatio": 1.3,
        "priceToBook": 2.7,
        "debtToEquity": 0.9,
        "returnOnEquity": 0.18,
        "profitMargins": 0.22,
        "revenueGrowth": 0.14,
        "earningsGrowth": 0.11,
        "dividendYield": 0.01,
        "currentPrice": 1640.5,
        "targetMeanPrice": 1725.0,
        "fiftyTwoWeekHigh": 1794.0,
        "fiftyTwoWeekLow": 1363.55,
    }


def test_get_fundamentals_info_prefers_exact_suffixed_ticker_before_fallbacks():
    client = PostgresClient.__new__(PostgresClient)
    mock_session = MagicMock()

    class _Result:
        def __init__(self, value):
            self._value = value

        def first(self):
            return self._value

    calls = []

    def execute(statement, params):
        calls.append(params["ticker"])
        if params["ticker"] == "HDFCBANK.BO":
            return _Result(
                {
                    "ticker": "HDFCBANK.BO",
                    "updated_at": datetime(2026, 4, 14, 10, 0, 0),
                    "name": "HDFC BANK LTD BO",
                    "industry": "Banks",
                    "sector": "Financial Services",
                    "market_cap": 2_000_000,
                    "pe_ratio": 21.0,
                    "forward_pe": 19.0,
                    "peg_ratio": 1.4,
                    "price_to_book": 2.9,
                    "debt_to_equity": 0.8,
                    "return_on_equity": 0.19,
                    "profit_margins": 0.23,
                    "revenue_growth": 0.15,
                    "earnings_growth": 0.12,
                    "dividend_yield": 0.02,
                    "current_price": 1655.0,
                    "target_mean_price": 1740.0,
                    "fifty_two_week_high": 1800.0,
                    "fifty_two_week_low": 1370.0,
                }
            )
        if params["ticker"] == "HDFCBANK.NS":
            return _Result(
                {
                    "ticker": "HDFCBANK.NS",
                    "updated_at": datetime(2026, 4, 13, 10, 0, 0),
                    "name": "HDFC BANK LTD NS",
                    "industry": "Banks",
                    "sector": "Financial Services",
                    "market_cap": 1_000_000,
                    "pe_ratio": 19.0,
                    "forward_pe": 17.0,
                    "peg_ratio": 1.2,
                    "price_to_book": 2.5,
                    "debt_to_equity": 0.9,
                    "return_on_equity": 0.18,
                    "profit_margins": 0.22,
                    "revenue_growth": 0.14,
                    "earnings_growth": 0.11,
                    "dividend_yield": 0.01,
                    "current_price": 1640.0,
                    "target_mean_price": 1720.0,
                    "fifty_two_week_high": 1790.0,
                    "fifty_two_week_low": 1360.0,
                }
            )
        return _Result(None)

    mock_session.execute.side_effect = execute

    @contextmanager
    def fake_session():
        yield mock_session

    client.get_session = fake_session  # type: ignore[method-assign]

    result = client.get_fundamentals_info("HDFCBANK.BO")

    assert calls[0] == "HDFCBANK.BO"
    assert result["ticker"] == "HDFCBANK"
    assert result["updated_at"] == "2026-04-14T10:00:00"
    assert result["name"] == "HDFC BANK LTD BO"
    assert result["marketCap"] == 2_000_000


def test_get_fundamentals_info_uses_best_snapshot_for_unsuffixed_requests():
    client = PostgresClient.__new__(PostgresClient)
    mock_session = MagicMock()

    class _Result:
        def __init__(self, value):
            self._value = value

        def first(self):
            return self._value

    calls = []

    def execute(statement, params):
        calls.append(params["ticker"])
        if params["ticker"] == "HDFCBANK":
            return _Result(
                {
                    "ticker": "HDFCBANK",
                    "updated_at": datetime(2026, 4, 10, 9, 0, 0),
                    "name": "HDFC BANK LTD",
                    "industry": None,
                    "sector": None,
                    "market_cap": 900_000,
                    "pe_ratio": None,
                    "forward_pe": None,
                    "peg_ratio": None,
                    "price_to_book": None,
                    "debt_to_equity": None,
                    "return_on_equity": None,
                    "profit_margins": None,
                    "revenue_growth": None,
                    "earnings_growth": None,
                    "dividend_yield": None,
                    "current_price": None,
                    "target_mean_price": None,
                    "fifty_two_week_high": None,
                    "fifty_two_week_low": None,
                }
            )
        if params["ticker"] == "HDFCBANK.NS":
            return _Result(
                {
                    "ticker": "HDFCBANK.NS",
                    "updated_at": datetime(2026, 4, 14, 9, 0, 0),
                    "name": "HDFC BANK LTD NS",
                    "industry": "Banks",
                    "sector": "Financial Services",
                    "market_cap": 1_500_000,
                    "pe_ratio": 20.5,
                    "forward_pe": 18.0,
                    "peg_ratio": 1.4,
                    "price_to_book": 2.8,
                    "debt_to_equity": 0.85,
                    "return_on_equity": 0.19,
                    "profit_margins": 0.23,
                    "revenue_growth": 0.16,
                    "earnings_growth": 0.12,
                    "dividend_yield": 0.02,
                    "current_price": 1660.0,
                    "target_mean_price": 1750.0,
                    "fifty_two_week_high": 1810.0,
                    "fifty_two_week_low": 1380.0,
                }
            )
        return _Result(None)

    mock_session.execute.side_effect = execute

    @contextmanager
    def fake_session():
        yield mock_session

    client.get_session = fake_session  # type: ignore[method-assign]

    result = client.get_fundamentals_info("HDFCBANK")

    assert calls == ["HDFCBANK", "HDFCBANK.NS", "HDFCBANK.BO"]
    assert result["ticker"] == "HDFCBANK"
    assert result["updated_at"] == "2026-04-14T09:00:00"
    assert result["name"] == "HDFC BANK LTD NS"
    assert result["marketCap"] == 1_500_000
    assert result["returnOnEquity"] == 0.19


def test_get_fundamentals_info_returns_missing_data_shape_when_no_row_exists():
    client = PostgresClient.__new__(PostgresClient)
    mock_session = MagicMock()

    class _Result:
        def __init__(self, value):
            self._value = value

        def first(self):
            return self._value

    def execute(statement, params):
        assert params["ticker"] in {"HDFCBANK", "HDFCBANK.NS", "HDFCBANK.BO"}
        return _Result(None)

    mock_session.execute.side_effect = execute

    @contextmanager
    def fake_session():
        yield mock_session

    client.get_session = fake_session  # type: ignore[method-assign]

    result = client.get_fundamentals_info("HDFCBANK")

    assert result["ticker"] == "HDFCBANK"
    assert result == {
        "ticker": "HDFCBANK",
        "ticker_found": False,
        "has_data": False,
        "updated_at": None,
        "latest_date": None,
    }
