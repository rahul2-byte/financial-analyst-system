"""Direct provider and deterministic-tool execution for AgentLoop."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
from app.core.research_schemas import EvidenceProvenance
from app.core.resources import RuntimeResources
from quant.fundamentals import FundamentalScanner
from quant.indicators import TechnicalScanner

_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "data:fetch_stock_data",
            "description": "Fetch verified OHLCV data for a Yahoo Finance ticker.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "period": {"type": "string"},
                    "interval": {"type": "string"},
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "data:fetch_fundamentals",
            "description": "Fetch verified company fundamentals for a Yahoo Finance ticker.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "news:fetch_news",
            "description": "Fetch recent news for a Yahoo Finance ticker.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analysis:run_fundamental_scan",
            "description": "Run deterministic fundamental analysis using verified provider data.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analysis:run_technical_scan",
            "description": "Run deterministic RSI, MACD, and Bollinger analysis using verified OHLCV data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "period": {"type": "string"},
                    "interval": {"type": "string"},
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "interaction:ask_user",
            "description": "Ask one concise clarification question before continuing research.",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"],
            },
        },
    },
]


class FinancialToolRunner:
    """Execute the finite set of tools supported by the current runtime."""

    def __init__(self, resources: RuntimeResources) -> None:
        self.resources = resources
        self._ohlcv_by_request: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        self._fundamentals_by_ticker: dict[str, dict[str, Any]] = {}

    def definitions(self) -> list[dict[str, Any]]:
        return [dict(definition) for definition in _TOOL_DEFINITIONS]

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "analysis:run_fundamental_scan":
            ticker = str(arguments.get("ticker", "")).strip()
            if not ticker:
                return {
                    "success": False,
                    "error": "Ticker is required for fundamental analysis",
                }
            data = self._fundamentals_by_ticker.get(ticker)
            if data is None:
                fetched = self.resources.yf_fetcher.fetch_company_fundamentals(ticker)
                if isinstance(fetched, dict) and "error" not in fetched:
                    data = fetched
                    self._fundamentals_by_ticker[
                        str(fetched.get("ticker") or ticker)
                    ] = fetched
            if data:
                arguments = {**arguments, "raw_data": data}
            raw_data = arguments.get("raw_data", {})
            if not isinstance(raw_data, dict) or not raw_data:
                return {"success": False, "error": "No fundamental data provided"}
            if not any(
                raw_data.get(key) is not None
                for key in (
                    "peRatio",
                    "forwardPE",
                    "priceToBook",
                    "debtToEquity",
                    "profitMargins",
                    "returnOnEquity",
                )
            ):
                return {
                    "success": False,
                    "error": "No usable fundamental metrics provided",
                }
            return FundamentalScanner().scan(raw_data)

        if name == "analysis:run_technical_scan":
            ticker = str(arguments.get("ticker", "")).strip()
            if not ticker:
                return {
                    "success": False,
                    "error": "Ticker is required for technical analysis",
                    "retryable": False,
                }
            period, interval = (
                str(arguments.get("period", "1y")),
                str(arguments.get("interval", "1d")),
            )
            key = (ticker, period, interval)
            rows = self._ohlcv_by_request.get(key)
            if rows is None:
                fetched = self.resources.yf_fetcher.fetch_stock_price(ticker, period, interval)
                rows = fetched.get("data") if isinstance(fetched, dict) else None
                if not rows:
                    return {
                        "success": False,
                        "error": "No OHLCV data returned for ticker",
                    }
                self._ohlcv_by_request[key] = rows
            return TechnicalScanner.get_signal_summary(pd.DataFrame(rows))

        if name == "data:fetch_stock_data":
            ticker = str(arguments.get("ticker", "")).strip()
            value = self.resources.yf_fetcher.fetch_stock_price(
                ticker,
                str(arguments.get("period", "1y")),
                str(arguments.get("interval", "1d")),
            )
            rows = value.get("data") if isinstance(value, dict) else None
            if not rows:
                return {
                    "success": False,
                    "error": "No evidence returned for data:fetch_stock_data",
                }
            issues = value.get("quality_issues", []) if isinstance(value, dict) else []
            if any(
                isinstance(issue, dict) and issue.get("blocking", True)
                for issue in issues
            ):
                return {
                    "success": False,
                    "error": "Market data failed deterministic quality validation",
                    "quality_issues": issues,
                }
            ticker = str(value.get("ticker") or ticker)
            period, interval = (
                str(value.get("period", arguments.get("period", "1y"))),
                str(value.get("interval", arguments.get("interval", "1d"))),
            )
            self._ohlcv_by_request[(ticker, period, interval)] = rows
            result = {
                "ticker": ticker,
                "period": period,
                "interval": interval,
                "row_count": len(rows),
                "period_return_pct": _period_return_pct(rows[0], rows[-1]),
                "first": rows[0],
                "latest": rows[-1],
                "provenance": value.get("provenance")
                or _provider_provenance(
                    "historical_prices", ticker, _row_timestamp(rows[-1])
                ),
            }
            return {"success": True, "data": result, "provenance": result["provenance"]}

        if name == "data:fetch_fundamentals":
            ticker = str(arguments.get("ticker", "")).strip()
            value = self.resources.yf_fetcher.fetch_company_fundamentals(ticker)
            if isinstance(value, dict) and "error" not in value:
                self._fundamentals_by_ticker[str(value.get("ticker") or ticker)] = value
        elif name == "news:fetch_news":
            ticker = str(arguments.get("ticker", "")).strip()
            articles = self.resources.yf_fetcher.fetch_news(ticker, int(arguments.get("limit", 10)))
            value = [
                article.model_dump(mode="json")
                if hasattr(article, "model_dump")
                else dict(article)
                for article in articles
            ]
        else:
            return {"success": False, "error": f"Unknown tool: {name}"}
        if not value:
            return {"success": False, "error": f"No evidence returned for {name}"}
        dataset = (
            "fundamentals_snapshot"
            if name == "data:fetch_fundamentals"
            else "news_snapshot"
        )
        provenance = _provider_provenance(
            dataset,
            str(arguments.get("ticker", "")),
            _news_timestamp(value),
            "degraded" if name == "data:fetch_fundamentals" else "verified",
        )
        return {"success": True, "data": value, "provenance": provenance}


def _provider_provenance(
    dataset: str,
    instrument: str,
    observed_at: datetime | None,
    quality_status: str = "verified",
) -> dict[str, Any]:
    observed = observed_at or datetime.now(UTC)
    return EvidenceProvenance(
        source="yfinance",
        dataset=dataset,
        instrument=instrument,
        observed_at=observed,
        ingested_at=datetime.now(UTC),
        version="yfinance-live-v1",
        quality_status=quality_status,
    ).model_dump(mode="json")


def _row_timestamp(row: dict[str, Any]) -> datetime | None:
    raw = row.get("Datetime", row.get("Date", row.get("datetime", row.get("date"))))
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw).astimezone(UTC)
    except ValueError:
        return None


def _news_timestamp(items: Any) -> datetime | None:
    timestamps = [
        _parse_timestamp(item.get("published_at"))
        for item in items
        if isinstance(item, dict)
    ]
    valid = [timestamp for timestamp in timestamps if timestamp is not None]
    return max(valid) if valid else None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).astimezone(UTC)
    except ValueError:
        return None


def _period_return_pct(first: dict[str, Any], latest: dict[str, Any]) -> float | None:
    first_value = first.get("Close", first.get("close"))
    latest_value = latest.get("Close", latest.get("close"))
    if first_value is None or latest_value is None:
        return None
    try:
        first_close = float(first_value)
        latest_close = float(latest_value)
    except (TypeError, ValueError):
        return None
    if first_close == 0:
        return None
    return round((latest_close / first_close - 1) * 100, 4)
