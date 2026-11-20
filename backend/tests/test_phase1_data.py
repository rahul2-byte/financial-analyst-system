"""Phase 1 regression tests for data adapters and news pipeline (F-47..F-57)."""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import numpy as np
import pandas as pd
import pytest
from app.config import settings
from data.news_pipeline.connectors import (
    TinyFishSearchConnector,
    _parse_datetime,
)
from data.news_pipeline.extractor import ArticleExtractor
from data.news_pipeline.models import CompanyContext, NewsPipelineRecord
from data.news_pipeline.normalize import DuplicateDetector
from data.news_pipeline.quality import QualityScorer
from data.news_pipeline.runner import NewsPipelineRunner
from data.news_pipeline.tinyfish_client import TinyFishSearchClient
from data.providers import yfinance as yf_module
from data.providers.upstox import UpstoxError, UpstoxFetcher
from data.providers.yfinance import YFinanceFetcher
from data.quality import (
    trading_days_between,
    validate_market_freshness,
    validate_market_records,
)
from data.retry import (
    ProviderUnavailable,
    acall_with_retry,
    backoff_delay,
    call_with_retry,
)
from quant.fundamentals import FundamentalScanner

IST_OFFSET = "+05:30"


def _ist(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC) - timedelta(
        hours=5, minutes=30
    )


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PROVIDER_RETRY_BASE_SECONDS", 0.0)
    monkeypatch.setattr(settings, "PROVIDER_RETRY_MAX_SECONDS", 0.0)


def _daily_frame(dates: list[str], **overrides: Any) -> pd.DataFrame:
    n = len(dates)
    frame = pd.DataFrame(
        {
            "Open": np.full(n, 100.0),
            "High": np.full(n, 102.0),
            "Low": np.full(n, 99.0),
            "Close": np.full(n, 101.0),
            "Adj Close": np.full(n, 101.0),
            "Volume": np.full(n, 1000.0),
        },
        index=pd.DatetimeIndex(pd.to_datetime(dates), name="Date"),
    )
    for column, values in overrides.items():
        frame[column] = values
    return frame


# --------------------------------------------------------------------- F-47
def test_f47_naive_timestamps_localised_to_ist_regardless_of_host_tz(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "America/Los_Angeles"
    time.tzset()
    try:
        monkeypatch.setattr(
            yf_module.yf, "download", lambda *a, **k: _daily_frame(["2026-11-17"])
        )
        fetcher = YFinanceFetcher(clock=lambda: _ist(2026, 11, 18, 18, 0))
        result = fetcher.fetch_stock_price("RELIANCE", "1mo", "1d")
    finally:
        if previous is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = previous
        time.tzset()
    assert result["data"][0]["Date"].endswith(IST_OFFSET)
    # Midnight IST on the 17th is 18:30 UTC on the 16th; not shifted by host tz.
    assert result["provenance"]["observed_at"].startswith("2026-11-16T18:30")


def test_f47_intraday_naive_timestamps_are_localised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _daily_frame(["2026-11-17 09:15", "2026-11-17 09:30"])
    frame.index.name = "Datetime"
    monkeypatch.setattr(yf_module.yf, "download", lambda *a, **k: frame)
    fetcher = YFinanceFetcher(clock=lambda: _ist(2026, 11, 17, 9, 40))
    result = fetcher.fetch_stock_price("TCS", "1d", "15m")
    assert all(row["Datetime"].endswith(IST_OFFSET) for row in result["data"])


@pytest.mark.parametrize(
    ("clock", "last_bar", "expected"),
    [
        (_ist(2026, 11, 18, 10, 0), "2026-11-18", True),  # Wed, intraday, today's bar
        (_ist(2026, 11, 18, 15, 30), "2026-11-18", False),  # closed
        (_ist(2026, 11, 18, 10, 0), "2026-11-17", False),  # bar is yesterday
    ],
)
def test_f47_partial_session_flag(
    monkeypatch: pytest.MonkeyPatch, clock: datetime, last_bar: str, expected: bool
) -> None:
    monkeypatch.setattr(
        yf_module.yf, "download", lambda *a, **k: _daily_frame([last_bar])
    )
    result = YFinanceFetcher(clock=lambda: clock).fetch_stock_price("INFY", "5d", "1d")
    assert result["provenance"]["partial_session"] is expected
    codes = {issue["code"] for issue in result["quality_issues"]}
    assert ("PARTIAL_SESSION" in codes) is expected
    if expected:
        assert result["data"][-1]["partial_session"] is True
        assert result["provenance"]["quality_status"] == "degraded"


# --------------------------------------------------------------------- F-48
def test_f48_missing_ohlc_rows_are_dropped_not_zero_filled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _daily_frame(["2026-11-10", "2026-11-11", "2026-11-12"])
    frame.loc[frame.index[1], "Close"] = np.nan
    seen: dict[str, Any] = {}

    def download(*args: Any, **kwargs: Any) -> pd.DataFrame:
        seen.update(kwargs)
        return frame

    monkeypatch.setattr(yf_module.yf, "download", download)
    fetcher = YFinanceFetcher(clock=lambda: _ist(2026, 11, 14, 18, 0))
    rows = fetcher.fetch_ohlcv(
        "SBIN", datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 11, 14, tzinfo=UTC)
    )
    assert len(rows) == 2
    assert all(row.close > 0 and row.open > 0 for row in rows)
    assert seen["auto_adjust"] is False
    provenance = fetcher.last_ohlcv_provenance
    assert provenance["dropped_rows"] == 1
    assert provenance["auto_adjust"] is False


def test_f48_fetch_ohlcv_runs_quality_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _daily_frame(["2026-11-10", "2026-11-11"], High=[90.0, 90.0])
    monkeypatch.setattr(yf_module.yf, "download", lambda *a, **k: frame)
    fetcher = YFinanceFetcher(clock=lambda: _ist(2026, 11, 14, 18, 0))
    with pytest.raises(ValueError, match="INVALID_OHLC"):
        fetcher.fetch_ohlcv(
            "SBIN",
            datetime(2026, 11, 1, tzinfo=UTC),
            datetime(2026, 11, 14, tzinfo=UTC),
        )


def test_f48_price_provenance_records_auto_adjust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        yf_module.yf, "download", lambda *a, **k: _daily_frame(["2026-11-17"])
    )
    fetcher = YFinanceFetcher(clock=lambda: _ist(2026, 11, 18, 18, 0))
    result = fetcher.fetch_stock_price("SBIN")
    assert result["provenance"]["auto_adjust"] is False


# --------------------------------------------------------------------- F-49
class _FakeTicker:
    def __init__(self, info: dict[str, Any] | None = None, delay: float = 0.0) -> None:
        self._info = info or {}
        self._delay = delay

    @property
    def info(self) -> dict[str, Any]:
        time.sleep(self._delay)
        return self._info


def test_f49_fundamentals_normalise_units_and_carry_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = {
        "shortName": "Acme",
        "marketCap": 1.5e12,
        "currency": "INR",
        "debtToEquity": 45.3,
        "trailingPE": 20.0,
    }
    monkeypatch.setattr(yf_module.yf, "Ticker", lambda t: _FakeTicker(info))
    fetcher = YFinanceFetcher(clock=lambda: _ist(2026, 11, 18, 18, 0))
    result = fetcher.fetch_company_fundamentals("ACME")
    assert result["debtToEquity"] == pytest.approx(0.453)
    assert result["marketCap"] == 1.5e12  # raw INR kept (backward compatible)
    assert result["marketCapCrore"] == pytest.approx(150_000.0)
    assert result["units"]["debtToEquity"] == "ratio"
    assert result["units"]["marketCapCrore"] == "INR crore"
    assert result["source"] == "yfinance"
    assert result["as_of"].startswith("2026-11-18T12:30")

    text = FundamentalScanner.scan(result)
    assert "0.45x" in text["financial_health_analysis"]
    assert "45.3" not in text["financial_health_analysis"]
    assert "INR 150,000 crore" in text["raw_data_context"]


def test_f49_info_has_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "YFINANCE_INFO_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(settings, "PROVIDER_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(
        yf_module.yf, "Ticker", lambda t: _FakeTicker({"shortName": "x"}, delay=0.5)
    )
    started = time.monotonic()
    with pytest.raises(ProviderUnavailable):
        YFinanceFetcher().fetch_company_fundamentals("ACME")
    assert time.monotonic() - started < 0.4


def test_f49_scanner_without_units_keeps_legacy_behaviour() -> None:
    result = FundamentalScanner.scan({"debtToEquity": 150})
    assert "150.0" in result["financial_health_analysis"]
    assert "x;" not in result["financial_health_analysis"]


# --------------------------------------------------------------------- F-50
def test_f50_macro_returns_value_as_of_currency_source_and_logs_failures(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class Ticker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def history(self, period: str) -> pd.DataFrame:
            if self.symbol == "^INDIAVIX":
                raise ValueError("boom")
            index = pd.DatetimeIndex(["2026-11-17"], tz="UTC")
            return pd.DataFrame({"Close": [83.5]}, index=index)

    monkeypatch.setattr(yf_module.yf, "Ticker", Ticker)
    monkeypatch.setattr(settings, "PROVIDER_RETRY_ATTEMPTS", 1)
    with caplog.at_level(logging.WARNING):
        macro = YFinanceFetcher().fetch_macro_indicators()
    usd = macro["USD_INR"]
    assert usd["value"] == 83.5
    assert usd["currency"] == "INR"
    assert usd["source"] == "yfinance"
    assert usd["as_of"].startswith("2026-11-17")
    assert macro["INDIA_VIX"]["value"] is None
    assert "ValueError" in macro["INDIA_VIX"]["error"]
    assert "INDIA_VIX" in caplog.text


# --------------------------------------------------------------------- F-51
def _status_error(code: int, headers: dict[str, str] | None = None) -> Exception:
    request = httpx.Request("GET", "https://example.test")
    return httpx.HTTPStatusError(
        "err",
        request=request,
        response=httpx.Response(code, headers=headers, request=request),
    )


def test_f51_retry_recovers_after_transient_failures() -> None:
    calls: list[int] = []
    delays: list[float] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("down")
        return "ok"

    assert call_with_retry(flaky, provider="p", attempts=3, sleep=delays.append) == "ok"
    assert len(calls) == 3
    assert len(delays) == 2


def test_f51_retry_is_bounded_and_typed_with_429_status() -> None:
    calls: list[int] = []

    def limited() -> None:
        calls.append(1)
        raise _status_error(429)

    with pytest.raises(ProviderUnavailable) as raised:
        call_with_retry(limited, provider="p", attempts=3, sleep=lambda s: None)
    assert len(calls) == 3
    assert raised.value.status_code == 429
    assert raised.value.provider == "p"


def test_f51_retry_honours_retry_after_and_skips_non_retryable() -> None:
    delays: list[float] = []
    calls: list[int] = []

    def limited() -> None:
        calls.append(1)
        raise _status_error(429, {"retry-after": "2"})

    with pytest.raises(ProviderUnavailable):
        call_with_retry(limited, provider="p", attempts=2, sleep=delays.append)
    assert delays == [2.0]

    def forbidden() -> None:
        raise _status_error(401)

    with pytest.raises(httpx.HTTPStatusError):
        call_with_retry(forbidden, provider="p", attempts=3, sleep=lambda s: None)


def test_f51_backoff_is_exponential_capped_and_jittered() -> None:
    low = backoff_delay(3, base_delay=1.0, max_delay=100.0, jitter=lambda: 0.0)
    high = backoff_delay(3, base_delay=1.0, max_delay=100.0, jitter=lambda: 1.0)
    assert (low, high) == (2.0, 4.0)
    assert backoff_delay(10, base_delay=1.0, max_delay=5.0, jitter=lambda: 1.0) == 5.0


@pytest.mark.asyncio
async def test_f51_async_retry_recovers() -> None:
    calls: list[int] = []

    async def flaky() -> int:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow")
        return 7

    async def no_sleep(_: float) -> None:
        return None

    assert await acall_with_retry(flaky, provider="p", sleep=no_sleep) == 7


def test_f51_upstox_retries_429_then_raises_upstox_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setattr(settings, "FINAI_QUOTA_DB", str(tmp_path / "quota.sqlite3"))
    calls: list[int] = []

    def fake_get(*args: Any, **kwargs: Any) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, request=httpx.Request("GET", "https://example.test"))

    monkeypatch.setattr("httpx.get", fake_get)
    with pytest.raises(UpstoxError) as raised:
        UpstoxFetcher(access_token="t").resolve_instrument("RELIANCE")
    assert len(calls) == settings.PROVIDER_RETRY_ATTEMPTS
    assert raised.value.status_code == 429


@pytest.mark.asyncio
async def test_f51_tinyfish_empty_key_is_unavailable_not_no_news() -> None:
    client = TinyFishSearchClient(api_key="")
    with pytest.raises(ProviderUnavailable, match="api_key_missing"):
        await client.search(
            query="q",
            num_results=1,
            start_published_date=datetime(2026, 1, 1, tzinfo=UTC),
        )

    connector = TinyFishSearchConnector(client=client)
    company = CompanyContext(ticker="RELIANCE.NS", company_name="Reliance Industries")
    assert await connector.fetch(company, time_window_days=7) == []
    assert connector.last_run_stats["status"] == "unavailable"
    assert connector.last_run_stats["query_failures"] == 1

    runner = NewsPipelineRunner(connectors=[connector])
    assert await runner.run(company=company, time_window_days=7) == []
    assert runner.last_run_stats["status"] == "unavailable"
    assert "api_key_missing" in runner.last_run_stats["unavailable_reasons"]


@pytest.mark.asyncio
async def test_f51_tinyfish_client_retries_transient_errors() -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"results": [{"title": "t", "url": "https://x.test"}]}

    class Http:
        attempts = 0

        async def __aenter__(self) -> Http:  # noqa: PYI034
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def get(self, url: str, **kwargs: Any) -> Response:
            Http.attempts += 1
            if Http.attempts == 1:
                raise httpx.ConnectError("down")
            return Response()

    client = TinyFishSearchClient(api_key="k", client_factory=lambda timeout: Http())
    results = await client.search(
        query="q", num_results=1, start_published_date=datetime(2026, 1, 1, tzinfo=UTC)
    )
    assert Http.attempts == 2
    assert results[0]["title"] == "t"


# --------------------------------------------------------------------- F-53
def test_f53_trading_days_skip_weekends_and_supplied_holidays() -> None:
    # Fri 2026-11-13 -> Mon 2026-11-16 is one trading day.
    assert trading_days_between(date(2026, 11, 13), date(2026, 11, 16)) == 1
    assert (
        trading_days_between(
            date(2026, 11, 13), date(2026, 11, 17), holidays={date(2026, 11, 16)}
        )
        == 1
    )


def test_f53_weekend_does_not_make_daily_data_stale() -> None:
    # Friday's bar viewed on Sunday: 0 trading days old; strict 1-day limit holds.
    assert (
        validate_market_freshness(
            observed_at=_ist(2026, 11, 13), as_of=_ist(2026, 11, 15, 12), max_age_days=1
        )
        == ()
    )
    stale = validate_market_freshness(
        observed_at=_ist(2026, 11, 9), as_of=_ist(2026, 11, 13, 12), max_age_days=3
    )
    assert stale[0].code == "STALE_DATA"


def test_f53_intraday_threshold_counts_session_minutes_only() -> None:
    observed = _ist(2026, 11, 13, 15, 15)  # Friday close
    as_of = _ist(2026, 11, 16, 9, 20)  # Monday open: 20 session minutes elapsed
    assert (
        validate_market_freshness(
            observed_at=observed, as_of=as_of, max_age_days=3, interval="15m"
        )
        == ()
    )
    stale = validate_market_freshness(
        observed_at=observed, as_of=as_of, max_age_days=3, interval="5m"
    )
    assert stale[0].code == "STALE_DATA"


def _row(ts: str) -> dict[str, Any]:
    return {
        "ticker": "T.NS",
        "Date": ts,
        "open": 10.0,
        "high": 11.0,
        "low": 9.0,
        "close": 10.5,
        "volume": 1.0,
    }


def test_f53_order_duplicate_and_gap_checks() -> None:
    rows = [
        _row("2026-11-02T00:00:00+05:30"),
        _row("2026-11-03T00:00:00+05:30"),
        _row("2026-11-03T00:00:00+05:30"),
        _row("2026-11-02T00:00:00+05:30"),
        _row("2026-11-30T00:00:00+05:30"),
    ]
    issues = validate_market_records(
        rows, "T.NS", datetime(2026, 11, 30, tzinfo=UTC), interval="1d"
    )
    codes = [issue.code for issue in issues]
    assert "DUPLICATE_TIMESTAMP" in codes
    assert "OUT_OF_ORDER_TIMESTAMP" in codes
    gap = next(issue for issue in issues if issue.code == "DATA_GAP")
    assert gap.blocking is False


def test_f53_clean_series_has_no_gap_or_order_issue() -> None:
    rows = [_row(f"2026-11-{day:02d}T00:00:00+05:30") for day in (2, 3, 4, 5, 6, 9)]
    assert (
        validate_market_records(
            rows, "T.NS", datetime(2026, 11, 9, tzinfo=UTC), interval="1d"
        )
        == ()
    )


# --------------------------------------------------------------------- F-54..57
def _record(title: str, when: datetime, *, words: int = 100, **kw: Any) -> Any:
    fields: dict[str, Any] = {
        "ticker": "RELIANCE",
        "company_name": "Reliance Industries",
        "market": "IN",
        "url": f"https://example.com/{abs(hash(title))}",
        "canonical_url": f"https://example.com/{abs(hash(title))}",
        "title": title,
        "author": None,
        "snippet": "",
        "article_text": "x",
        "word_count": words,
        "publish_time": when,
        "retrieval_time": when,
        "source_domain": "example.com",
        "source_type": "rss",
        "source_tier": 2,
        "paywall_detected": False,
        "extraction_status": "full",
        "quality_score": 50.0,
        "relevance_check": True,
        "is_duplicate": False,
        "cluster_id": None,
        "query_intent": "x",
        "search_provider": "rss",
        "pipeline_version": "1",
    }
    fields.update(kw)
    return NewsPipelineRecord(**fields)


def test_f54_titles_with_different_numbers_are_not_merged() -> None:
    when = datetime(2026, 11, 1, 10, tzinfo=UTC)
    records = [
        _record("Reliance profit rises 12% in Q3", when),
        _record("Reliance profit rises 21% in Q3", when),
    ]
    result = DuplicateDetector().mark_duplicates(records)
    assert [item.is_duplicate for item in result] == [False, False]


def test_f54_titles_with_same_numbers_are_still_merged() -> None:
    when = datetime(2026, 11, 1, 10, tzinfo=UTC)
    records = [
        _record("Reliance profit rises 12% in Q3", when),
        _record("Reliance Q3 profit rises 12%", when),
    ]
    result = DuplicateDetector().mark_duplicates(records)
    assert sorted(item.is_duplicate for item in result) == [False, True]


def test_f55_naive_publish_time_does_not_crash_and_future_is_penalised() -> None:
    kwargs: dict[str, Any] = {
        "source_tier": 2,
        "extraction_status": "full",
        "relevance_check": True,
        "word_count": 200,
        "is_duplicate": False,
    }
    naive = datetime.now(UTC).replace(tzinfo=None)
    assert QualityScorer.score(publish_time=naive, **kwargs) > 0
    fresh = QualityScorer.score(publish_time=datetime.now(UTC), **kwargs)
    future = QualityScorer.score(
        publish_time=datetime.now(UTC) + timedelta(days=30), **kwargs
    )
    undated = QualityScorer.score(publish_time=None, **kwargs)
    assert future < fresh
    assert future == undated


def test_f56_epoch_seconds_vs_milliseconds_and_naive_ist() -> None:
    expected = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    seconds = int(expected.timestamp())
    assert _parse_datetime(seconds) == expected
    assert _parse_datetime(seconds * 1000) == expected
    assert _parse_datetime(float(seconds)) == expected
    naive = _parse_datetime("2026-11-01T17:30:00")
    assert naive == expected  # 17:30 IST == 12:00 UTC
    assert _parse_datetime(datetime(2026, 11, 1, 17, 30)) == expected  # noqa: DTZ001 - naive on purpose
    assert _parse_datetime(None) is None
    assert _parse_datetime(True) is None


@pytest.mark.asyncio
async def test_f56_undated_items_are_flagged_in_stats() -> None:
    class Client:
        async def search(self, **kwargs: Any) -> list[dict[str, Any]]:
            return [
                {
                    "title": "Reliance Industries announces plan",
                    "url": "https://example.com/a",
                    "snippet": "Reliance Industries news",
                }
            ]

    connector = TinyFishSearchConnector(client=Client(), max_queries_per_run=1)
    company = CompanyContext(ticker="RELIANCE.NS", company_name="Reliance Industries")
    results = await connector.fetch(company, time_window_days=7)
    assert results and results[0].publish_time is None
    assert connector.last_run_stats["undated_count"] == len(results)


def test_f57_paywall_stub_is_partial_and_quality_capped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = ArticleExtractor()
    stub = ("Reliance Industries results. " * 40) + " Subscribe to read the rest."
    monkeypatch.setattr(extractor, "_extract_with_trafilatura", lambda url: stub)
    result = extractor.extract(
        url="https://example.com/story",
        source_domain="example.com",
        company_name="Reliance Industries",
        ticker="RELIANCE",
        snippet="",
        source_type="rss",
    )
    assert result.paywall_detected is True
    assert result.extraction_status == "partial"

    kwargs: dict[str, Any] = {
        "source_tier": 1,
        "extraction_status": "full",
        "publish_time": datetime.now(UTC),
        "relevance_check": True,
        "word_count": 900,
        "is_duplicate": False,
    }
    assert QualityScorer.score(**kwargs) > 30
    assert QualityScorer.score(paywall_detected=True, **kwargs) <= 30
