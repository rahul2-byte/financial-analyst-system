from __future__ import annotations

import asyncio
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from app.core.agent_loop import FinancialToolRunner
from app.core.agent_loop.tool_runner import _ohlcv_key
from app.core.resources import RuntimeResources
from data.news_pipeline.tinyfish_client import TinyFishSearchClient
from data.providers.upstox import UpstoxError, UpstoxFetcher
from data.providers.yfinance import YFinanceFetcher
from data.retry import ProviderUnavailable
from finai.session_runtime import ResearchRunner

RATIOS = {
    "data": [
        {"name": "P/E", "company_value": "20.15"},
        {"name": "ROE", "company_value": "8.94%"},
    ]
}


class YF:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def fetch_company_fundamentals(self, ticker: str) -> dict:
        self.calls.append(("fundamentals", ticker))
        return {"ticker": ticker, "peRatio": 12, "source": "yfinance"}

    def fetch_stock_price(self, ticker: str, period: str, interval: str) -> dict:
        self.calls.append(("price", ticker, period, interval))
        return {
            "ticker": ticker,
            "data": [
                {"Open": 10, "High": 11, "Low": 9, "Close": 10, "Volume": 100},
                {"Open": 11, "High": 13, "Low": 10, "Close": 12, "Volume": 120},
            ],
        }


class Upstox:
    def __init__(self, *, fail: bool = False, isin: str | None = "INE1") -> None:
        self.fail = fail
        self.isin = isin

    def resolve_instrument(self, query: str) -> list[dict]:
        if self.fail:
            raise UpstoxError("down")
        return [{"isin": self.isin}] if self.isin else []

    def fetch_fundamentals(self, isin: str) -> dict:
        return {"isin": isin, "source": "upstox", "peRatio": 20.0}


def _scan_runner(upstox: Upstox | None) -> tuple[FinancialToolRunner, YF]:
    yf = YF()
    resources = RuntimeResources(
        llm_service=object(), yf_fetcher=yf, upstox_fetcher=upstox
    )
    return FinancialToolRunner(resources), yf


@pytest.mark.asyncio
async def test_fundamental_scan_skips_yfinance_when_upstox_succeeds() -> None:
    runner, yf = _scan_runner(Upstox())
    result = await runner.execute("analysis:run_fundamental_scan", {"ticker": "ABC"})
    assert yf.calls == []
    assert result["key_values"]
    assert runner._fundamentals_by_ticker.get("ABC")["source"] == "upstox"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "upstox",
    [Upstox(fail=True), Upstox(isin=None), None],
    ids=["fail", "no-isin", "off"],
)
async def test_fundamental_scan_falls_back_to_yfinance(upstox) -> None:
    runner, yf = _scan_runner(upstox)
    await runner.execute("analysis:run_fundamental_scan", {"ticker": "ABC"})
    assert yf.calls == [("fundamentals", "ABC")]
    assert runner._fundamentals_by_ticker.get("ABC")["source"] == "yfinance"


def _bundle_fetcher(monkeypatch, get) -> UpstoxFetcher:
    monkeypatch.setattr(UpstoxFetcher, "_get", get)
    return UpstoxFetcher(access_token="t")


def test_concurrent_bundle_matches_sequential_merge(monkeypatch) -> None:
    barrier = threading.Barrier(2, timeout=5)  # both must run at once to pass
    payloads: dict[str, dict] = {
        "key-ratios": RATIOS,
        "profile": {"data": {"sector": "S", "company_profile": "P"}},
        "balance-sheet": {"data": [1]},
    }

    def get(self, path, params=None, **kw):
        suffix = path.rsplit("/", 1)[1]
        if suffix in ("profile", "cash-flow"):
            barrier.wait()
        if suffix not in payloads:
            raise UpstoxError(f"{suffix} missing")
        return {"status": "success", **payloads[suffix]}

    data = _bundle_fetcher(monkeypatch, get).fetch_fundamentals("INE")
    # Warnings keep the fixed endpoint order regardless of completion order.
    assert data["warnings"] == [
        "cash_flow: cash-flow missing",
        "income_statement: income-statement missing",
        "share_holdings: share-holdings missing",
        "corporate_actions: corporate-actions missing",
        "competitors: competitors missing",
    ]
    assert data["balance_sheet"] == [1]
    assert data["sector"] == "S" and data["description"] == "P"
    assert data["peRatio"] == 20.15 and data["returnOnEquity"] == 0.0894
    # Key order equals the sequential loop's (warnings appears at first failure).
    assert list(data)[:6] == [
        "isin",
        "source",
        "profile",
        "balance_sheet",
        "warnings",
        "key_ratios",
    ]


def test_bundle_uses_one_shared_client(monkeypatch) -> None:
    clients: set[int] = set()

    def get(self, path, params=None, *, client=None):
        clients.add(id(client))
        return {"status": "success", "data": None}

    _bundle_fetcher(monkeypatch, get).fetch_fundamentals("INE")
    assert len(clients) == 1 and id(None) not in clients


def test_ohlcv_key_merges_only_same_instrument() -> None:
    assert _ohlcv_key("RELIANCE", "1y", "1d") == _ohlcv_key("reliance.ns", "1y", "1d")
    assert _ohlcv_key("RELIANCE", "1y", "1d") != _ohlcv_key("RELIANCE.BO", "1y", "1d")
    assert _ohlcv_key("RELIANCE", "1y", "1d") != _ohlcv_key("RELIANCE", "1y", "1wk")
    assert _ohlcv_key("^NSEI", "1y", "1d")[0] == "^NSEI"
    assert _ohlcv_key("bad ticker!", "1y", "1d")[0] == "bad ticker!"


@pytest.mark.asyncio
async def test_spelling_variants_share_one_download() -> None:
    runner, yf = _scan_runner(None)
    await runner.execute("analysis:run_technical_scan", {"ticker": "RELIANCE"})
    await runner.execute("analysis:run_technical_scan", {"ticker": "RELIANCE.NS"})
    assert len([c for c in yf.calls if c[0] == "price"]) == 1


@pytest.mark.asyncio
async def test_instrument_search_does_not_block_event_loop() -> None:
    class SlowUpstox:
        def resolve_instrument(self, query: str) -> list[dict]:
            time.sleep(0.3)
            return [{"trading_symbol": "HDFCBANK", "short_name": "HDFC Bank"}]

    runner = ResearchRunner(
        RuntimeResources(
            llm_service=object(), yf_fetcher=object(), upstox_fetcher=SlowUpstox()
        ),
        "guided",
    )
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    resolution, source = await runner._resolve_instrument_context(
        [], "Analyse the HDFC BANK stock", uuid4()
    )
    task.cancel()
    assert source == "provider_search"
    assert resolution.ticker == "HDFCBANK.NS"
    assert ticks >= 10  # loop kept running during the 0.3 s sync search


@pytest.mark.asyncio
async def test_instrument_search_timeout_becomes_unresolved(monkeypatch) -> None:
    monkeypatch.setattr("finai.session_runtime.INSTRUMENT_SEARCH_TIMEOUT_SECONDS", 0.05)

    class HungUpstox:
        def resolve_instrument(self, query: str) -> list[dict]:
            time.sleep(0.5)
            return []

    runner = ResearchRunner(
        RuntimeResources(
            llm_service=object(), yf_fetcher=object(), upstox_fetcher=HungUpstox()
        ),
        "guided",
    )
    resolution, source = await runner._resolve_instrument_context(
        [], "Analyse the HDFC BANK stock", uuid4()
    )
    assert resolution.status == "unresolved" and source == "provider_search"


def test_info_timeout_is_not_retried(monkeypatch) -> None:
    calls = {"n": 0}

    class Obj:
        @property
        def info(self):
            calls["n"] += 1
            raise TimeoutError("hung")

    monkeypatch.setattr("data.providers.yfinance.yf.Ticker", lambda _t: Obj())
    monkeypatch.setattr(
        "data.providers.yfinance.call_with_timeout", lambda fn, timeout: fn()
    )
    with pytest.raises(ProviderUnavailable):
        YFinanceFetcher().fetch_company_fundamentals("ABC")
    assert calls["n"] == 1


def test_download_gets_timeout(monkeypatch) -> None:
    seen: dict = {}

    def fake_download(*args, **kwargs):
        seen.update(kwargs)

    monkeypatch.setattr("data.providers.yfinance.yf.download", fake_download)
    YFinanceFetcher().fetch_stock_price("ABC", "1y", "1d")
    assert seen["timeout"] == 10


@pytest.mark.asyncio
async def test_tinyfish_session_reuses_one_client(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.FINAI_QUOTA_DB", str(tmp_path / "q.db"))
    created: list[object] = []

    class FakeClient:
        async def __aenter__(self):
            created.append(self)
            return self

        async def __aexit__(self, *exc):
            return None

        async def get(self, url, headers=None, params=None):
            return httpx.Response(
                200, json={"results": []}, request=httpx.Request("GET", url)
            )

    client = TinyFishSearchClient(api_key="k", client_factory=lambda _t: FakeClient())
    client.quota.per_second = 100
    when = datetime.now(UTC)
    async with client.session():
        for _ in range(3):
            await client.search(query="q", num_results=1, start_published_date=when)
    assert len(created) == 1
    await client.search(query="q", num_results=1, start_published_date=when)
    assert len(created) == 2  # outside a session: per-request client as before
