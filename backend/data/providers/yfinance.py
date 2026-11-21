"""
YFinance data provider for the Financial Intelligence Platform.

This module provides:
- OHLCV data fetching
- Company fundamentals
- Financial statements
- Macro indicators
- News fetching

Usage:
    from data.providers.yfinance import YFinanceFetcher

    fetcher = YFinanceFetcher()
    ohlcv_data = fetcher.fetch_ohlcv("RELIANCE.NS", start_date, end_date)
"""

import functools
import logging
import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
import numpy as np
import pandas as pd
import yfinance as yf
from app.config import settings
from app.core.observability import observe
from app.core.ticker import Ticker, parse_ticker
from app.observability.provider_archive import ProviderArchive
from data.interfaces.fetcher import IDataFetcher
from data.quality import (
    IST,
    DataQualityIssue,
    is_partial_daily_bar,
    parse_timestamp,
    utc_now,
    validate_market_freshness,
    validate_market_records,
)
from data.retry import (
    ProviderUnavailable,
    call_with_retry,
    call_with_timeout,
    is_retryable,
    provider_retry_kwargs,
)
from data.schemas.market import OHLCVData
from data.schemas.text import NewsArticle

logger = logging.getLogger(__name__)

INDIAN_STOCK_SUFFIX = ".NS"
_INR_CRORE = 10_000_000


def _is_indian(ticker: str) -> bool:
    return ticker.endswith((".NS", ".BO"))


def _localize(value: Any, ticker: str) -> datetime | None:
    """Return a timezone-aware datetime; naive values get the exchange timezone.

    Indian tickers are localised to Asia/Kolkata regardless of the host timezone;
    other tickers default naive values to UTC.
    """
    if value is None:
        return None
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(stamp):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize(IST if _is_indian(ticker) else UTC)
    elif _is_indian(ticker):
        stamp = stamp.tz_convert(IST)
    return stamp.to_pydatetime(warn=False)  # type: ignore[no-any-return]


def _finite(value: Any) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


YFINANCE_DOWNLOAD_TIMEOUT_SECONDS = 10


def _retryable_except_timeout(exc: BaseException) -> bool:
    return not isinstance(exc, (TimeoutError, httpx.TimeoutException)) and (
        is_retryable(exc)
    )


class ReplayYFinanceFetcher:
    """Strict offline yfinance replacement backed only by archived payloads."""

    def __init__(self, archive: ProviderArchive, snapshots: dict[str, str]) -> None:
        self._archive = archive
        self._snapshots = snapshots

    def fetch_stock_price(
        self, ticker: str, period: str = "1mo", interval: str = "1d"
    ) -> dict[str, Any]:
        del ticker, period, interval
        return self._payload("fetch_stock_price")

    def fetch_company_fundamentals(self, ticker: str) -> dict[str, Any]:
        del ticker
        return self._payload("fetch_fundamentals")

    def fetch_news(self, ticker: str, limit: int = 10) -> list[dict[str, Any]]:
        del ticker, limit
        payload = self._payload("fetch_news")
        if not isinstance(payload, list):
            raise TypeError("replay snapshot has an invalid news payload")
        return payload

    def _payload(self, operation: str) -> Any:
        content_hash = self._snapshots.get(operation)
        if not content_hash:
            raise RuntimeError(f"replay snapshot missing for {operation}")
        snapshot = self._archive.load(content_hash)
        if snapshot.provider != "yfinance" or snapshot.operation != operation:
            raise RuntimeError(f"replay snapshot does not match {operation}")
        return snapshot.payload


class YFinanceFetcher(IDataFetcher):
    """
    Data fetcher using yfinance library.

    Handles:
    - Auto-formatting of Indian stock tickers
    - Multi-index column handling
    - Error handling for missing data
    """

    def __init__(self, clock: Callable[[], datetime] = utc_now) -> None:
        self._clock = clock
        self.last_ohlcv_provenance: dict[str, Any] = {}

    def _call(self, function: Callable[[], Any]) -> Any:
        return call_with_retry(function, provider="yfinance", **provider_retry_kwargs())

    def _format_ticker(self, ticker: str | Ticker) -> str:
        """
        Auto-append .NS for Indian stocks if no suffix is provided.

        Args:
            ticker: Raw ticker symbol

        Returns:
            Formatted ticker with appropriate suffix
        """
        return parse_ticker(ticker).provider_format_yfinance(
            default_exchange_suffix=INDIAN_STOCK_SUFFIX,
        )

    def _parse_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Parse yfinance DataFrame to handle multi-index columns.

        Args:
            df: Raw DataFrame from yfinance

        Returns:
            Cleaned DataFrame with simple columns
        """
        if df is None or df.empty:
            return df

        df = df.reset_index()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        return df

    def _safe_get_value(
        self, row: pd.Series, col: str, default: float | None = None
    ) -> float | None:
        """
        Safely extract a value from a DataFrame row.

        Args:
            row: DataFrame row
            col: Column name
            default: Default value if not found

        Returns:
            Float value, or ``default`` (None unless given) when missing or NaN
        """
        if col not in row:
            return default

        val = row[col]

        if isinstance(val, (pd.Series, np.ndarray)):
            if len(val) > 0:
                val = getattr(val, "iloc", val)[0]
            else:
                return default

        if pd.isna(val):
            return default

        return float(val)

    def _safe_get_date(
        self, row: pd.Series, ticker: str = INDIAN_STOCK_SUFFIX
    ) -> datetime | None:
        """
        Safely extract date from a DataFrame row.

        Args:
            row: DataFrame row

        Returns:
            datetime object or None
        """
        date_col = "Date" if "Date" in row.index else None

        if not date_col:
            for idx in row.index:
                if isinstance(idx, tuple):
                    for item in idx:
                        if "date" in str(item).lower():
                            date_col = item
                            break

        if not date_col:
            return None

        date_val = row[date_col]

        if date_val is None:
            return None

        return _localize(date_val, ticker)

    @observe(name="Tool:YFinance:FetchOHLCV")
    def fetch_ohlcv(
        self, ticker: str, start_date: datetime, end_date: datetime
    ) -> list[OHLCVData]:
        """
        Fetch historical OHLCV data.

        Rows with any missing OHLC/volume value are dropped (never zero-filled)
        and the remainder is run through the market-data quality validator;
        blocking findings raise ``ValueError``. Prices are unadjusted
        (``auto_adjust=False``); the
        adjusted close is carried separately. Provenance for the last call is in
        ``last_ohlcv_provenance``.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date
            end_date: End date

        Returns:
            List of OHLCVData objects
        """
        formatted_ticker = self._format_ticker(ticker)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        df = self._call(
            lambda: yf.download(
                formatted_ticker,
                start=start_str,
                end=end_str,
                progress=False,
                auto_adjust=False,
                timeout=YFINANCE_DOWNLOAD_TIMEOUT_SECONDS,
            )
        )

        if df is None or df.empty:
            return []

        df = self._parse_dataframe(df)

        results: list[OHLCVData] = []
        validation_rows: list[dict[str, Any]] = []
        dropped = 0

        for _, row in df.iterrows():
            date_val = self._safe_get_date(row, formatted_ticker)
            fields = {
                name: self._safe_get_value(row, name)
                for name in ("Open", "High", "Low", "Close", "Volume")
            }
            if date_val is None or any(value is None for value in fields.values()):
                dropped += 1
                continue
            adjusted = (
                self._safe_get_value(row, "Adj Close")
                if "Adj Close" in row.index
                else None
            )
            open_, high, low, close, volume = (
                float(fields[name])  # type: ignore[arg-type]
                for name in ("Open", "High", "Low", "Close", "Volume")
            )
            validation_rows.append(
                {
                    "ticker": formatted_ticker,
                    "Date": date_val.isoformat(),
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
            )
            results.append(
                OHLCVData(
                    ticker=formatted_ticker,
                    date=date_val,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=int(volume),
                    adjusted_close=adjusted,
                )
            )

        now = self._clock()
        issues = (
            validate_market_records(
                validation_rows,
                formatted_ticker,
                results[-1].date if results else now,
                interval="1d",
            )
            if results
            else ()
        )
        self.last_ohlcv_provenance = {
            "source": "yfinance",
            "instrument": formatted_ticker,
            "auto_adjust": False,
            "adjustment": "unadjusted_ohlc_with_separate_adjusted_close",
            "timezone": "Asia/Kolkata" if _is_indian(formatted_ticker) else "UTC",
            "dropped_rows": dropped,
            "ingested_at": now.isoformat(),
            "quality_issues": [issue.model_dump(mode="json") for issue in issues],
        }
        blocking = [issue for issue in issues if issue.blocking]
        if blocking:
            codes = sorted({issue.code for issue in blocking})
            raise ValueError(f"yfinance OHLCV rejected by quality validator: {codes}")
        return results

    @observe(name="Tool:YFinance:FetchPrice")
    def fetch_stock_price(
        self, ticker: str, period: str = "1mo", interval: str = "1d"
    ) -> dict[str, Any]:
        """
        Fetch stock price by period and interval.

        Naive timestamps are localised to Asia/Kolkata for Indian tickers (never
        the host timezone). A daily bar dated today before the 15:30 IST close is
        flagged ``partial_session``.

        Args:
            ticker: Stock ticker
            period: Time period (e.g., "1mo", "1y")
            interval: Data interval (e.g., "1d", "1h")

        Returns:
            Dictionary with price data
        """
        formatted_ticker = self._format_ticker(ticker)

        df = self._call(
            lambda: yf.download(
                formatted_ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False,
                timeout=YFINANCE_DOWNLOAD_TIMEOUT_SECONDS,
            )
        )

        if df is None or df.empty:
            return {"error": "No data found", "ticker": formatted_ticker}

        df = self._parse_dataframe(df)

        date_col = (
            "Date"
            if "Date" in df.columns
            else "Datetime"
            if "Datetime" in df.columns
            else df.columns[0]
        )
        localized = df[date_col].map(lambda value: _localize(value, formatted_ticker))
        df[date_col] = [
            str(stamp) if stamp is not None else str(raw)
            for stamp, raw in zip(localized, df[date_col], strict=True)
        ]
        last_bar = next((stamp for stamp in reversed(list(localized)) if stamp), None)

        records = df.to_dict(orient="records")
        normalized_records = [
            {
                "ticker": formatted_ticker,
                "open": row.get("Open", row.get("open")),
                "high": row.get("High", row.get("high")),
                "low": row.get("Low", row.get("low")),
                "close": row.get("Close", row.get("close")),
                "volume": row.get("Volume", row.get("volume")),
                "Date": row.get(date_col),
            }
            for row in records
        ]
        ingested_at = self._clock()
        observed_at = ingested_at
        if normalized_records and isinstance(normalized_records[-1].get("Date"), str):
            parsed = parse_timestamp(normalized_records[-1]["Date"])
            if parsed is not None:
                observed_at = parsed.astimezone(UTC)
        partial_session = bool(
            _is_indian(formatted_ticker)
            and interval == "1d"
            and last_bar is not None
            and is_partial_daily_bar(last_bar, ingested_at)
        )
        quality_issues: list[DataQualityIssue] = list(
            validate_market_records(
                normalized_records,
                formatted_ticker,
                observed_at,
                interval=interval,
            )
        )
        quality_issues += validate_market_freshness(
            observed_at=observed_at,
            as_of=ingested_at,
            max_age_days=settings.MARKET_DATA_MAX_AGE_DAYS,
            interval=interval,
        )
        if partial_session:
            records[-1]["partial_session"] = True
            quality_issues.append(
                DataQualityIssue(
                    code="PARTIAL_SESSION",
                    message="latest daily bar is today's session and is not yet closed (before 15:30 IST)",
                    blocking=False,
                )
            )
        has_adjusted_close = all(row.get("Adj Close") is not None for row in records)
        if any(issue.blocking for issue in quality_issues):
            quality_status = "rejected"
        elif quality_issues:
            quality_status = "degraded"
        else:
            quality_status = "verified"

        return {
            "ticker": formatted_ticker,
            "period": period,
            "interval": interval,
            "data": records,
            "provenance": {
                "source": "yfinance",
                "dataset": "historical_prices",
                "instrument": formatted_ticker,
                "observed_at": observed_at.isoformat(),
                "ingested_at": ingested_at.isoformat(),
                "version": "yfinance-live-v1",
                "quality_status": quality_status,
                "currency": "INR" if _is_indian(formatted_ticker) else None,
                "timezone": "Asia/Kolkata" if _is_indian(formatted_ticker) else "UTC",
                "auto_adjust": False,
                "adjustment": (
                    "adjusted_close_available" if has_adjusted_close else "unadjusted"
                ),
                "partial_session": partial_session,
                "as_of": observed_at.isoformat(),
                "source_url": f"https://finance.yahoo.com/quote/{quote(formatted_ticker, safe='^=.-')}/history/",
            },
            "quality_issues": [
                issue.model_dump(mode="json") for issue in quality_issues
            ],
        }

    @observe(name="Tool:YFinance:FetchFundamentals")
    def fetch_company_fundamentals(self, ticker: str) -> dict[str, Any]:
        """
        Fetch company fundamental data with normalised units and provenance.

        Normalisation: ``debtToEquity`` is returned as a ratio (yfinance reports
        a percent), ``marketCap`` stays raw INR and ``marketCapCrore`` adds INR
        crore for INR-quoted tickers. ``units``, ``as_of`` and ``source`` describe
        every value. ``info`` is fetched with a timeout and bounded retries.

        Args:
            ticker: Stock ticker

        Returns:
            Dictionary with fundamental metrics
        """
        formatted_ticker = self._format_ticker(ticker)
        ticker_obj = yf.Ticker(formatted_ticker)
        timeout = float(settings.YFINANCE_INFO_TIMEOUT_SECONDS)
        try:
            info = call_with_retry(
                lambda: call_with_timeout(lambda: ticker_obj.info, timeout),
                provider="yfinance",
                retryable=_retryable_except_timeout,
                **provider_retry_kwargs(),
            )
        except TimeoutError as exc:
            # A hung ``info`` is not retried (each attempt costs the full timeout).
            raise ProviderUnavailable(
                "yfinance", "TimeoutError after 1 attempts", attempts=1
            ) from exc

        if not info:
            return {"error": "No fundamental info found", "ticker": formatted_ticker}

        currency = str(
            info.get("currency") or ("INR" if _is_indian(formatted_ticker) else "")
        ).upper()
        market_cap = _finite(info.get("marketCap"))
        debt_percent = _finite(info.get("debtToEquity"))
        units = {
            "marketCap": currency or "unknown",
            "marketCapCrore": "INR crore",
            "debtToEquity": "ratio",
            "returnOnEquity": "fraction",
            "profitMargins": "fraction",
            "revenueGrowth": "fraction",
            "earningsGrowth": "fraction",
            "dividendYield": "provider_reported",
            "currentPrice": currency or "unknown",
            "targetMeanPrice": currency or "unknown",
            "fiftyTwoWeekHigh": currency or "unknown",
            "fiftyTwoWeekLow": currency or "unknown",
        }

        return {
            "ticker": formatted_ticker,
            "name": info.get("shortName", ""),
            "industry": info.get("industry", ""),
            "sector": info.get("sector", ""),
            "marketCap": info.get("marketCap"),
            "marketCapCrore": (
                market_cap / _INR_CRORE
                if market_cap is not None and currency == "INR"
                else None
            ),
            "peRatio": info.get("trailingPE"),
            "forwardPE": info.get("forwardPE"),
            "pegRatio": info.get("pegRatio"),
            "priceToBook": info.get("priceToBook"),
            # yfinance reports debtToEquity as a percent (45.3 means 0.453x).
            "debtToEquity": (
                debt_percent / 100.0 if debt_percent is not None else None
            ),
            "returnOnEquity": info.get("returnOnEquity"),
            "profitMargins": info.get("profitMargins"),
            "revenueGrowth": info.get("revenueGrowth"),
            "earningsGrowth": info.get("earningsGrowth"),
            "dividendYield": info.get("dividendYield"),
            "currentPrice": info.get("currentPrice"),
            "targetMeanPrice": info.get("targetMeanPrice"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
            "currency": currency or None,
            "units": units,
            "as_of": self._clock().isoformat(),
            "source": "yfinance",
        }

    @observe(name="Tool:YFinance:FetchFinancials")
    def fetch_financial_statements(self, ticker: str) -> dict[str, Any]:
        """
        Fetch financial statements.

        Args:
            ticker: Stock ticker

        Returns:
            Dictionary with income statement, balance sheet, cash flow
        """
        formatted_ticker = self._format_ticker(ticker)
        ticker_obj = yf.Ticker(formatted_ticker)

        income_stmt = ticker_obj.financials
        balance_sheet = ticker_obj.balance_sheet
        cash_flow = ticker_obj.cashflow

        def format_df(df: pd.DataFrame | None) -> dict[str, Any]:
            if df is None or df.empty:
                return {}

            df = df.copy()
            df.columns = [
                col.strftime("%Y-%m-%d") if isinstance(col, datetime) else str(col)
                for col in df.columns
            ]
            df = df.where(pd.notnull(df), None)
            return df.to_dict()

        return {
            "ticker": formatted_ticker,
            "income_statement": format_df(income_stmt),
            "balance_sheet": format_df(balance_sheet),
            "cash_flow": format_df(cash_flow),
        }

    @observe(name="Tool:YFinance:FetchMacro")
    def fetch_macro_indicators(self) -> dict[str, Any]:
        """
        Fetch key macro indicators for Indian markets.

        Returns:
            ``{name: {value, as_of, currency, source, unit}}``. A failed indicator
            has ``value`` None plus an ``error`` string (and is logged).
        """
        # name -> (symbol, currency, unit)
        macros: dict[str, tuple[str, str | None, str]] = {
            "NIFTY_50": ("^NSEI", None, "index_points"),
            "INDIA_VIX": ("^INDIAVIX", None, "index_points"),
            "USD_INR": ("INR=X", "INR", "INR_per_USD"),
            "CRUDE_OIL": ("CL=F", "USD", "USD_per_barrel"),
            "GOLD": ("GC=F", "USD", "USD_per_troy_ounce"),
        }

        results: dict[str, Any] = {}

        for name, (symbol, currency, unit) in macros.items():
            entry: dict[str, Any] = {
                "value": None,
                "as_of": None,
                "currency": currency,
                "unit": unit,
                "source": "yfinance",
            }
            try:
                history = self._call(
                    functools.partial(yf.Ticker(symbol).history, period="5d")
                )
                if history is not None and not history.empty:
                    close_price = history["Close"].iloc[-1]
                    if isinstance(close_price, pd.Series):
                        close_price = close_price.iloc[0]
                    entry["value"] = _finite(close_price)
                    stamp = pd.Timestamp(history.index[-1])
                    if stamp.tzinfo is None:
                        stamp = stamp.tz_localize(UTC)
                    entry["as_of"] = stamp.tz_convert(UTC).isoformat()
                else:
                    entry["error"] = "no data returned"
            except Exception as exc:  # noqa: BLE001 - one field must not fail the snapshot
                logger.warning("Macro indicator %s (%s) failed: %s", name, symbol, exc)
                entry["error"] = f"{type(exc).__name__}: {exc}"
            results[name] = entry

        return results

    @observe(name="Tool:YFinance:FetchNews")
    def fetch_news(self, ticker: str, limit: int = 10) -> list[NewsArticle]:
        """
        Fetch latest news for a ticker.

        Args:
            ticker: Stock ticker
            limit: Maximum number of articles

        Returns:
            List of NewsArticle objects
        """
        formatted_ticker = self._format_ticker(ticker)
        ticker_obj = yf.Ticker(formatted_ticker)
        news_items = ticker_obj.news

        results: list[NewsArticle] = []

        for item in news_items[:limit]:
            content = (
                item.get("content") if isinstance(item.get("content"), dict) else item
            )
            title = str(content.get("title") or "").strip()
            canonical_url = content.get("canonicalUrl", {})
            url = str(
                canonical_url.get("url") or content.get("link", "")
                if isinstance(canonical_url, dict)
                else content.get("link", "")
            ).strip()
            if not title or not url:
                continue
            published = content.get("pubDate")
            pub_date = (
                datetime.fromisoformat(str(published))
                if published
                else datetime.fromtimestamp(
                    content.get("providerPublishTime", 0), tz=UTC
                )
            )
            provider = content.get("provider", {})

            article = NewsArticle(
                ticker=formatted_ticker,
                title=title,
                url=url,
                source=str(
                    provider.get("displayName", "Unknown")
                    if isinstance(provider, dict)
                    else content.get("publisher", "Unknown")
                ),
                published_date=pub_date,
                summary=content.get("summary"),
                content=str(
                    content.get("summary") or content.get("relatedTickers", [])
                ),
            )
            results.append(article)

        return results
