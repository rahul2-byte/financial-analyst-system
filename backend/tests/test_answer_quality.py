"""Answer-quality fixes: indicator key values, resolver ranking, source dedupe."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.agent_loop.runtime import _tool_message_content
from app.core.agent_loop.tool_runner import FinancialToolRunner
from app.core.instrument_resolution import resolve_instrument
from app.core.resources import RuntimeResources
from finai.plain import dedupe_sources, render_sources_plain


def _rows(count: int = 300) -> list[dict[str, Any]]:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(count):
        close = 100 + index * 0.5 + (index % 7)
        rows.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "open": close - 1,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": 1000 + index,
            }
        )
    return rows


class _YF:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []

    def fetch_stock_price(self, ticker: str, period: str, interval: str) -> dict:
        return {"ticker": ticker, "data": self.rows, "provenance": {}}

    def fetch_company_fundamentals(self, ticker: str) -> dict:
        return {
            "ticker": ticker,
            "peRatio": 21.5,
            "priceToBook": 3.2,
            "returnOnEquity": 0.18,
            "debtToEquity": 0.4,
            "marketCap": 123456,
        }


def _runner(yf: Any) -> FinancialToolRunner:
    return FinancialToolRunner(RuntimeResources(llm_service=object(), yf_fetcher=yf))


async def test_technical_key_values_survive_truncation() -> None:
    runner = _runner(_YF(_rows()))
    payload = await runner.execute(
        "analysis:run_technical_scan", {"ticker": "TCS.NS", "period": "1y"}
    )
    assert payload["success"] is True
    assert "key_values" in list(payload)[:3]
    key_values = payload["key_values"]
    for name in ("RSI_14", "SMA_20", "SMA_50", "SMA_200", "close", "as_of"):
        assert name in key_values
    assert key_values["RSI_14"] is not None
    assert key_values["SMA_50"] is not None
    # The full payload exceeds the model budget, so it gets truncated.
    assert len(json.dumps(payload, default=str)) > 7_500
    content = json.loads(_tool_message_content(payload))
    assert content["truncated"] is True
    assert "RSI_14=" in content["summary"]
    assert "SMA_50=" in content["summary"]


async def test_fundamental_key_values_present() -> None:
    runner = _runner(_YF())
    payload = await runner.execute(
        "analysis:run_fundamental_scan", {"ticker": "INFY.NS"}
    )
    assert payload["key_values"] == {
        "peRatio": 21.5,
        "priceToBook": 3.2,
        "returnOnEquity": 0.18,
        "debtToEquity": 0.4,
        "marketCap": 123456,
    }
    assert "peRatio=21.5" in payload["summary"]


async def test_empty_price_history_shows_delisted_message() -> None:
    runner = _runner(_YF([]))
    scan = await runner.execute(
        "analysis:run_technical_scan", {"ticker": "TATAMOTORS.NS"}
    )
    assert scan["success"] is False
    assert "No price data for TATAMOTORS.NS" in scan["error"]
    assert "symbol may have changed" in scan["error"]


_ADANI = [
    {"trading_symbol": "ONGC", "name": "OIL AND NATURAL GAS CORPORATION"},
    {"trading_symbol": "ADANIENT", "name": "ADANI ENTERPRISES LIMITED"},
    {"trading_symbol": "ONIDA", "name": "ONIDA LTD"},
]


def test_adani_news_query_resolves_to_adani() -> None:
    seen: list[str] = []

    def search(term: str) -> list[dict[str, Any]]:
        seen.append(term)
        return list(_ADANI)

    result = resolve_instrument("Latest news on Adani Enterprises", search)
    assert seen[0] == "ADANI ENTERPRISES"
    assert result.status == "resolved"
    assert result.ticker == "ADANIENT.NS"


def test_adani_ambiguous_ranks_name_match_first() -> None:
    items = [*_ADANI, {"trading_symbol": "ADANIX", "name": "ADANI ENTERPRISES X"}]
    result = resolve_instrument("adani", lambda term: items)
    assert result.status == "ambiguous"
    assert result.candidates[0]["trading_symbol"] in {"ADANIENT", "ADANIX"}
    assert result.candidates[-1]["trading_symbol"] in {"ONGC", "ONIDA"}


def test_infy_exact_symbol_still_resolves() -> None:
    items = [
        {"trading_symbol": "INFYTECH", "name": "INFY TECH"},
        {"trading_symbol": "INFY", "name": "INFOSYS LIMITED"},
    ]
    result = resolve_instrument("price of INFY", lambda term: items)
    assert result.status == "resolved"
    assert result.ticker == "INFY.NS"


def test_duplicate_sources_rendered_once() -> None:
    sources = [{"name": "fundamentals_snapshot", "url": "https://api.upstox.com"}] * 10
    assert len(dedupe_sources(sources)) == 1
    plain = render_sources_plain(sources)
    assert plain.count("https://api.upstox.com") == 1
    assert "Sources · 1" in plain
