"""Direct provider and deterministic-tool execution for AgentLoop."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pandas as pd
from app.config import settings
from app.core.prompts import PromptRegistry
from app.core.research_schemas import EvidenceProvenance
from app.core.resources import RuntimeResources
from app.observability.provider_archive import ProviderSnapshot
from data.news_pipeline.models import CompanyContext
from data.providers.upstox import UpstoxError
from data.quality import compare_vendor_values, utc_now, validate_market_records
from quant.fundamentals import FundamentalScanner
from quant.technical_engine import TechnicalEngine

_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "data:fetch_stock_data",
            "description": "",
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
            "name": "analysis:get_technical_overview",
            "description": "",
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
            "description": "",
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
            "description": "",
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
            "description": "",
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
            "description": "",
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
            "description": "",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "data:fetch_market_status",
            "description": "",
            "parameters": {
                "type": "object",
                "properties": {"exchange": {"type": "string"}},
                "required": ["exchange"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "data:fetch_market_holidays",
            "description": "",
            "parameters": {
                "type": "object",
                "properties": {"date": {"type": "string"}},
                "required": ["date"],
            },
        },
    },
]


class FinancialToolRunner:
    """Execute the finite set of tools supported by the current runtime."""

    def __init__(self, resources: RuntimeResources) -> None:
        self.resources = resources
        self.prompts = resources.prompts or PromptRegistry.bundled()
        self._mocked_tools: dict[str, list[Any]] = {}
        self._ohlcv_by_request: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        self._ohlcv_provenance_by_request: dict[
            tuple[str, str, str], dict[str, Any]
        ] = {}
        self._fundamentals_by_ticker: dict[str, dict[str, Any]] = {}
        self._fundamental_provenance_by_ticker: dict[str, dict[str, Any]] = {}
        self._technical_engine = TechnicalEngine()

    def set_mocked_tools(self, mocked_tools: list[dict[str, Any]]) -> None:
        """Install one-shot fixture responses for deterministic evaluation runs."""
        self._mocked_tools = {}
        for item in mocked_tools:
            name = item.get("name")
            if isinstance(name, str) and "response" in item:
                self._mocked_tools.setdefault(name, []).append(item["response"])

    def mocked_tools_remaining(self) -> int:
        return sum(len(items) for items in self._mocked_tools.values())

    def definitions(self) -> list[dict[str, Any]]:
        definitions = deepcopy(_TOOL_DEFINITIONS)
        keys = {
            "data:fetch_stock_data": "tools.data_fetch_stock_data.description",
            "analysis:get_technical_overview": "tools.analysis_get_technical_overview.description",
            "data:fetch_fundamentals": "tools.data_fetch_fundamentals.description",
            "news:fetch_news": "tools.news_fetch_news.description",
            "analysis:run_fundamental_scan": "tools.analysis_run_fundamental_scan.description",
            "analysis:run_technical_scan": "tools.analysis_run_technical_scan.description",
            "interaction:ask_user": "tools.interaction_ask_user.description",
            "data:fetch_market_status": "tools.data_fetch_market_status.description",
            "data:fetch_market_holidays": "tools.data_fetch_market_holidays.description",
        }
        for definition in definitions:
            function = cast(dict[str, Any], definition["function"])
            function["description"] = self.prompts.get(keys[function["name"]])
        return definitions

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        value: Any
        fixture = self._mocked_tools.get(name)
        if fixture:
            return fixture.pop(0)
        if name == "data:fetch_market_status":
            fetcher = self.resources.upstox_fetcher
            if fetcher is None:
                return {"success": False, "error": "Market status provider is unavailable"}
            try:
                data = fetcher.fetch_market_status(str(arguments["exchange"]))
            except UpstoxError as exc:
                return {"success": False, "error": str(exc)}
            return {
                "success": True,
                "data": data,
                "provenance": _provider_provenance(
                    "market_status", str(arguments["exchange"]), None, source="upstox"
                ),
            }

        if name == "data:fetch_market_holidays":
            fetcher = self.resources.upstox_fetcher
            if fetcher is None:
                return {"success": False, "error": "Market holiday provider is unavailable"}
            try:
                data = fetcher.fetch_market_holidays(str(arguments["date"]))
            except UpstoxError as exc:
                return {"success": False, "error": str(exc)}
            return {
                "success": True,
                "data": data,
                "provenance": _provider_provenance(
                    "market_holidays", str(arguments["date"]), None, source="upstox"
                ),
            }

        if name == "analysis:run_fundamental_scan":
            ticker = str(arguments.get("ticker", "")).strip()
            if not ticker:
                return {
                    "success": False,
                    "error": "Ticker is required for fundamental analysis",
                }
            data = self._fundamentals_by_ticker.get(ticker)
            provenance = dict(self._fundamental_provenance_by_ticker.get(ticker) or {})
            if data is None:
                fetched_fundamentals = (
                    self.resources.yf_fetcher.fetch_company_fundamentals(ticker)
                )
                if self.resources.upstox_fetcher is not None:
                    try:
                        matches = self.resources.upstox_fetcher.resolve_instrument(
                            ticker
                        )
                        isin = next(
                            (item.get("isin") for item in matches if item.get("isin")),
                            None,
                        )
                        if isin:
                            fetched_fundamentals = (
                                self.resources.upstox_fetcher.fetch_fundamentals(
                                    str(isin)
                                )
                            )
                            fetched_fundamentals["ticker"] = ticker
                    except UpstoxError:
                        pass
                if (
                    isinstance(fetched_fundamentals, dict)
                    and "error" not in fetched_fundamentals
                ):
                    data = fetched_fundamentals
                    self._fundamentals_by_ticker[
                        str(fetched_fundamentals.get("ticker") or ticker)
                    ] = fetched_fundamentals
                    provenance = _provider_provenance(
                        "fundamentals_snapshot", ticker, None, "degraded"
                    )
                    self._fundamental_provenance_by_ticker[
                        str(fetched_fundamentals.get("ticker") or ticker)
                    ] = provenance
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
            return {**FundamentalScanner().scan(raw_data), "provenance": provenance}

        if name == "analysis:get_technical_overview":
            ticker = str(arguments.get("ticker", "")).strip()
            if not ticker:
                return {
                    "success": False,
                    "error": "Ticker is required for technical analysis",
                }
            period, interval = (
                str(arguments.get("period", "1y")),
                str(arguments.get("interval", "1d")),
            )
            key = (ticker, period, interval)
            rows = self._ohlcv_by_request.get(key)
            provenance = dict(self._ohlcv_provenance_by_request.get(key) or {})
            if rows is None:
                fetched: dict[str, Any]
                if self.resources.upstox_fetcher is not None and interval == "1d":
                    try:
                        matches = self.resources.upstox_fetcher.resolve_instrument(
                            ticker
                        )
                        instrument_key = next(
                            (
                                item.get("instrument_key")
                                for item in matches
                                if item.get("instrument_key")
                            ),
                            None,
                        )
                        if instrument_key:
                            end = datetime.now(UTC)
                            start = end - timedelta(days=365)
                            rows = self.resources.upstox_fetcher.fetch_candles(
                                str(instrument_key), start=start, end=end
                            )
                            quality_issues = validate_market_records(
                                rows, ticker, utc_now()
                            )
                            if any(issue.blocking for issue in quality_issues):
                                raise UpstoxError(
                                    "Upstox OHLCV failed quality validation"
                                )
                            fetched = {
                                "data": rows,
                                "provenance": {
                                    "source": "upstox",
                                    "instrument": instrument_key,
                                },
                            }
                        else:
                            fetched = self.resources.yf_fetcher.fetch_stock_price(
                                ticker, period, interval
                            )
                    except UpstoxError:
                        fetched = self.resources.yf_fetcher.fetch_stock_price(
                            ticker, period, interval
                        )
                else:
                    fetched = self.resources.yf_fetcher.fetch_stock_price(
                        ticker, period, interval
                    )
                rows = fetched.get("data") if isinstance(fetched, dict) else None
                provenance = (
                    dict(fetched.get("provenance") or {})
                    if isinstance(fetched, dict)
                    else {}
                )
                if not rows:
                    return {
                        "success": False,
                        "error": "No OHLCV data returned for ticker",
                    }
                self._ohlcv_by_request[key] = rows
                self._ohlcv_provenance_by_request[key] = provenance
            snapshot = self._technical_engine.analyze(
                pd.DataFrame(rows),
                ticker=ticker,
                interval=interval,
                provenance=provenance,
            )
            output = snapshot.model_dump(mode="json")
            if self.resources.upstox_fetcher is not None and interval == "1d":
                try:
                    matches = self.resources.upstox_fetcher.resolve_instrument(ticker)
                    underlying = next(
                        (
                            item.get("instrument_key")
                            for item in matches
                            if item.get("instrument_key")
                        ),
                        None,
                    )
                    has_derivatives = any(
                        str(item.get("segment", "")).endswith("_FO")
                        or item.get("instrument_type") in {"FUT", "CE", "PE"}
                        for item in matches
                    )
                    if underlying and has_derivatives:
                        output["metadata"]["derivatives_context"] = (
                            self.resources.upstox_fetcher.fetch_derivatives(
                                str(underlying)
                            )
                        )
                except UpstoxError as exc:
                    output["warnings"].append(f"derivatives context unavailable: {exc}")
            return {"success": True, "data": output, "provenance": provenance}

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
                fetched = self.resources.yf_fetcher.fetch_stock_price(
                    ticker, period, interval
                )
                rows = fetched.get("data") if isinstance(fetched, dict) else None
                provenance = (
                    dict(fetched.get("provenance") or {})
                    if isinstance(fetched, dict)
                    else {}
                )
                if not rows:
                    return {
                        "success": False,
                        "error": "No OHLCV data returned for ticker",
                    }
                self._ohlcv_by_request[key] = rows
                self._ohlcv_provenance_by_request[key] = provenance
            else:
                provenance = dict(self._ohlcv_provenance_by_request.get(key) or {})
            snapshot = self._technical_engine.analyze(
                pd.DataFrame(rows),
                ticker=ticker,
                interval=interval,
                provenance=provenance,
            )
            return {
                "success": True,
                "data": snapshot.model_dump(mode="json"),
                "provenance": provenance,
            }

        if name == "data:fetch_stock_data":
            ticker = str(arguments.get("ticker", "")).strip()
            period = str(arguments.get("period", "1y"))
            interval = str(arguments.get("interval", "1d"))
            if self.resources.upstox_fetcher is not None and interval == "1d":
                try:
                    matches = self.resources.upstox_fetcher.resolve_instrument(ticker)
                    instrument_key = next(
                        (
                            item.get("instrument_key")
                            for item in matches
                            if item.get("instrument_key")
                        ),
                        None,
                    )
                    if not instrument_key:
                        raise UpstoxError("No Upstox instrument matched the ticker")
                    end = datetime.now(UTC)
                    rows = self.resources.upstox_fetcher.fetch_candles(
                        str(instrument_key),
                        start=end - timedelta(days=_period_days(period)),
                        end=end,
                    )
                    issues = validate_market_records(rows, ticker, utc_now())
                    if any(issue.blocking for issue in issues):
                        raise UpstoxError("Upstox OHLCV failed quality validation")
                    value = {
                        "ticker": ticker,
                        "period": period,
                        "interval": interval,
                        "data": rows,
                        "provenance": _provider_provenance(
                            "historical_prices",
                            ticker,
                            end,
                            source="upstox",
                            version="upstox-v3",
                            source_url="https://api.upstox.com",
                        ),
                    }
                except UpstoxError:
                    value = self.resources.yf_fetcher.fetch_stock_price(
                        ticker, period, interval
                    )
            else:
                value = self.resources.yf_fetcher.fetch_stock_price(
                    ticker, period, interval
                )
            raw_value = value.get("provenance") if isinstance(value, dict) else None
            raw_provenance = (
                dict(raw_value)
                if isinstance(raw_value, dict)
                else _provider_provenance("historical_prices", ticker, None)
            )
            self._archive("fetch_stock_price", value, raw_provenance)
            if isinstance(value, dict):
                value["provenance"] = raw_provenance
            rows = value.get("data") if isinstance(value, dict) else None
            if not rows:
                return {
                    "success": False,
                    "error": "No evidence returned for data:fetch_stock_data",
                }
            issues = value.get("quality_issues", []) if isinstance(value, dict) else []
            vendor_values = (
                value.get("vendor_values") if isinstance(value, dict) else None
            )
            if isinstance(vendor_values, dict):
                issues = [
                    *issues,
                    *(
                        issue.model_dump(mode="json")
                        for issue in compare_vendor_values(
                            vendor_values,
                            max_relative_difference=settings.VENDOR_MAX_RELATIVE_DIFFERENCE,
                        )
                    ),
                ]
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
            provenance = dict(value.get("provenance") or raw_provenance)
            self._ohlcv_provenance_by_request[(ticker, period, interval)] = provenance
            result = {
                "ticker": ticker,
                "period": period,
                "interval": interval,
                "row_count": len(rows),
                "period_return_pct": _period_return_pct(rows[0], rows[-1]),
                "period_return_basis": _period_return_basis(rows[0], rows[-1]),
                "corporate_action_adjusted": _has_adjusted_close(rows[0], rows[-1]),
                "first": rows[0],
                "latest": rows[-1],
                "provenance": provenance,
            }
            return {"success": True, "data": result, "provenance": result["provenance"]}

        if name == "data:fetch_fundamentals":
            ticker = str(arguments.get("ticker", "")).strip()
            source = "yfinance"
            if self.resources.upstox_fetcher is not None:
                try:
                    matches = self.resources.upstox_fetcher.resolve_instrument(ticker)
                    isin = next(
                        (item.get("isin") for item in matches if item.get("isin")),
                        None,
                    )
                    if not isin:
                        raise UpstoxError("No Upstox ISIN matched the ticker")
                    value = self.resources.upstox_fetcher.fetch_fundamentals(str(isin))
                    if not isinstance(value, dict) or not any(
                        value.get(key) is not None
                        for key in (
                            "peRatio",
                            "priceToBook",
                            "returnOnEquity",
                            "returnOnAssets",
                            "returnOnCapitalEmployed",
                            "evToEbitda",
                        )
                    ):
                        raise UpstoxError(
                            "Upstox returned no usable fundamental metrics"
                        )
                    value["ticker"] = ticker
                    source = "upstox"
                except UpstoxError:
                    value = self.resources.yf_fetcher.fetch_company_fundamentals(ticker)
            else:
                value = self.resources.yf_fetcher.fetch_company_fundamentals(ticker)
            if isinstance(value, dict) and "error" not in value:
                self._fundamentals_by_ticker[str(value.get("ticker") or ticker)] = value
        elif name == "news:fetch_news":
            ticker = str(arguments.get("ticker", "")).strip()
            limit = int(arguments.get("limit", 10))
            fundamentals = self._fundamentals_by_ticker.get(ticker) or {}
            company_name = str(fundamentals.get("name") or ticker).strip()
            if company_name == ticker and self.resources.upstox_fetcher is not None:
                try:
                    matches = self.resources.upstox_fetcher.resolve_instrument(ticker)
                    match: dict[str, Any] = next(
                        (
                            item
                            for item in matches
                            if item.get("trading_symbol")
                            == ticker.split(".", 1)[0].upper()
                        ),
                        {},
                    )
                    company_name = str(
                        match.get("short_name") or match.get("name") or ticker
                    ).strip()
                except UpstoxError:
                    pass
            pipeline = self.resources.news_pipeline_runner
            if pipeline is None:
                return {
                    "success": False,
                    "error": "News pipeline unavailable",
                    "evidence": {
                        "source": "news",
                        "status": "unavailable",
                        "reason": "pipeline unavailable",
                        "evidence_count": 0,
                    },
                }
            try:
                records = await pipeline.run(
                    company=CompanyContext(
                        ticker=ticker,
                        company_name=company_name,
                        nse_symbol=ticker.split(".", 1)[0],
                    ),
                    time_window_days=30,
                )
            except (TimeoutError, OSError, ConnectionError, RuntimeError) as exc:
                return {
                    "success": False,
                    "error": f"News source unavailable: {type(exc).__name__}",
                    "evidence": {
                        "source": "news",
                        "status": "unavailable",
                        "reason": type(exc).__name__,
                        "evidence_count": 0,
                    },
                }
            records = records[:limit]
            pipeline_stats = getattr(pipeline, "last_run_stats", {})
            value = [
                {
                    "title": record.title,
                    "url": record.url,
                    "summary": record.snippet,
                    "published_time": (
                        record.publish_time.isoformat()
                        if record.publish_time is not None
                        else None
                    ),
                    "source": record.search_provider,
                    "source_domain": record.source_domain,
                    "quality_score": record.quality_score,
                    "source_tier": record.source_tier,
                    "extraction_status": record.extraction_status,
                }
                for record in records
            ]
            sources = [
                {"name": record.source_domain, "url": record.url} for record in records
            ]
            source = "news_pipeline"
        else:
            return {"success": False, "error": f"Unknown tool: {name}"}
        dataset = (
            "fundamentals_snapshot"
            if name == "data:fetch_fundamentals"
            else "news_snapshot"
        )
        provenance = _provider_provenance(
            dataset,
            str(arguments.get("ticker", "")),
            _news_timestamp(value),
            (
                "degraded"
                if name == "news:fetch_news"
                and (
                    pipeline_stats.get("query_failures", 0)
                    or pipeline_stats.get("connector_failures", 0)
                    or pipeline_stats.get("degraded_fallback_count", 0)
                    or pipeline_stats.get("timeout", False)
                )
                else "verified"
                if source == "upstox"
                else "degraded"
                if name == "data:fetch_fundamentals"
                else "verified"
            ),
            source=source,
            version=(
                "news-pipeline-v1"
                if source == "news_pipeline"
                else "upstox-v2"
                if source == "upstox"
                else "yfinance-live-v1"
            ),
            source_url=(
                sources[0]["url"]
                if name == "news:fetch_news" and sources
                else "https://api.upstox.com"
                if source == "upstox"
                else (
                    f"https://finance.yahoo.com/quote/{arguments.get('ticker', '')}/"
                    f"{'history/' if dataset == 'historical_prices' else ''}"
                )
            ),
        )
        if name == "data:fetch_fundamentals" and isinstance(value, dict):
            self._fundamental_provenance_by_ticker[
                str(value.get("ticker") or arguments.get("ticker", ""))
            ] = provenance
        self._archive(
            name.removeprefix("data:").removeprefix("news:"), value, provenance
        )
        if not value:
            pipeline_stats = getattr(pipeline, "last_run_stats", {})
            return {
                "success": False,
                "error": f"No usable evidence returned for {name}",
                "evidence": {
                    "source": "news" if name == "news:fetch_news" else name,
                    "status": "unavailable",
                    "reason": (
                        "no usable documents"
                        if name == "news:fetch_news"
                        else "empty result"
                    ),
                    "evidence_count": 0,
                    "pipeline_stats": pipeline_stats,
                },
            }
        result = {"success": True, "data": value, "provenance": provenance}
        if name == "news:fetch_news":
            result["pipeline_stats"] = pipeline_stats
        if name == "news:fetch_news" and sources:
            result["sources"] = sources
        if name == "news:fetch_news":
            result["summary"] = json.dumps(
                {
                    "news_quality": dict(
                        getattr(
                            self.resources.news_pipeline_runner, "last_run_stats", {}
                        )
                    )
                },
                sort_keys=True,
            )
        return result

    def _archive(
        self, operation: str, payload: Any, provenance: dict[str, Any]
    ) -> None:
        archive = self.resources.provider_archive
        if archive is None:
            return
        stored = archive.store(
            ProviderSnapshot(
                provider=str(provenance.get("source", "unknown")),
                operation=operation,
                payload=payload,
                fetched_at=datetime.now(UTC),
            )
        )
        provenance["snapshot_hash"] = stored.content_hash


def _provider_provenance(
    dataset: str,
    instrument: str,
    observed_at: datetime | None,
    quality_status: str = "verified",
    *,
    source: str = "yfinance",
    version: str = "yfinance-live-v1",
    source_url: str | None = None,
) -> dict[str, Any]:
    observed = observed_at or datetime.now(UTC)
    resolved_source_url = source_url or (
        f"https://finance.yahoo.com/quote/{instrument}/"
        f"{'history/' if dataset == 'historical_prices' else ''}"
    )
    return EvidenceProvenance(
        source=source,
        dataset=dataset,
        instrument=instrument,
        observed_at=observed,
        ingested_at=datetime.now(UTC),
        version=version,
        quality_status=quality_status,
        currency="INR" if instrument.endswith((".NS", ".BO")) else None,
        timezone="Asia/Kolkata" if instrument.endswith((".NS", ".BO")) else "UTC",
        adjustment="unadjusted" if dataset == "historical_prices" else None,
        as_of=observed,
        source_url=resolved_source_url,
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
        _parse_timestamp(item.get("published_at", item.get("published_time")))
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
    first_value, latest_value = _return_values(first, latest)
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


def _return_values(
    first: dict[str, Any], latest: dict[str, Any]
) -> tuple[Any, Any]:
    adjusted_keys = ("Adj Close", "adjusted_close", "adj_close", "adjustedClose")
    for key in adjusted_keys:
        if first.get(key) is not None and latest.get(key) is not None:
            return first[key], latest[key]
    return (
        first.get("Close", first.get("close")),
        latest.get("Close", latest.get("close")),
    )


def _has_adjusted_close(first: dict[str, Any], latest: dict[str, Any]) -> bool:
    return any(
        first.get(key) is not None and latest.get(key) is not None
        for key in ("Adj Close", "adjusted_close", "adj_close", "adjustedClose")
    )


def _period_return_basis(first: dict[str, Any], latest: dict[str, Any]) -> str:
    return "adjusted_close" if _has_adjusted_close(first, latest) else "unadjusted_close"


def _period_days(period: str) -> int:
    return {
        "1d": 1,
        "5d": 5,
        "1mo": 31,
        "3mo": 92,
        "6mo": 184,
        "1y": 366,
        "2y": 731,
        "5y": 1_827,
    }.get(period, 366)
