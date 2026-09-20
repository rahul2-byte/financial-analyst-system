from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.core.agent_loop import FinancialToolRunner
from app.core.resources import RuntimeResources
from app.observability.provider_archive import ProviderArchive
from data.news_pipeline.models import NewsPipelineRecord


class FakeFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def fetch_stock_price(self, ticker: str, period: str, interval: str) -> dict:
        self.calls.append(("price", ticker, period, interval))
        return {
            "ticker": ticker,
            "period": period,
            "interval": interval,
            "data": [
                {"Open": 10, "High": 11, "Low": 9, "Close": 10, "Volume": 100},
                {"Open": 11, "High": 13, "Low": 10, "Close": 12, "Volume": 120},
            ],
        }

    def fetch_company_fundamentals(self, ticker: str) -> dict:
        self.calls.append(("fundamentals", ticker))
        return {"ticker": ticker, "peRatio": 12}

    def fetch_news(self, ticker: str, limit: int) -> list[dict]:
        self.calls.append(("news", ticker, limit))
        return [{"title": "headline"}]


def runner() -> tuple[FinancialToolRunner, FakeFetcher]:
    fetcher = FakeFetcher()
    return FinancialToolRunner(
        RuntimeResources(llm_service=object(), yf_fetcher=fetcher)
    ), fetcher


def test_definitions_are_the_current_finite_tool_surface() -> None:
    tool_runner, _ = runner()
    names = {item["function"]["name"] for item in tool_runner.definitions()}
    assert names == {
        "data:fetch_stock_data",
        "data:fetch_fundamentals",
        "news:fetch_news",
        "analysis:run_fundamental_scan",
        "analysis:run_technical_scan",
        "analysis:get_technical_overview",
        "interaction:ask_user",
    }


@pytest.mark.asyncio
async def test_stock_data_returns_summary_and_caches_for_analysis() -> None:
    tool_runner, fetcher = runner()
    result = await tool_runner.execute("data:fetch_stock_data", {"ticker": "ABC"})
    assert result["success"] is True
    assert result["data"]["period_return_pct"] == 20.0
    await tool_runner.execute("analysis:run_technical_scan", {"ticker": "ABC"})
    assert [call[0] for call in fetcher.calls] == ["price"]


@pytest.mark.asyncio
async def test_stock_data_prefers_valid_upstox_daily_candles() -> None:
    class FakeUpstox:
        def resolve_instrument(self, ticker: str) -> list[dict]:
            assert ticker == "ABC.NS"
            return [{"instrument_key": "NSE_EQ|ABC"}]

        def fetch_candles(self, instrument_key, *, start, end) -> list[dict]:
            assert instrument_key == "NSE_EQ|ABC"
            assert start < end
            return [
                {
                    "timestamp": "2026-09-16T00:00:00+05:30",
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10,
                    "volume": 100,
                },
                {
                    "timestamp": "2026-09-17T00:00:00+05:30",
                    "open": 10,
                    "high": 13,
                    "low": 10,
                    "close": 12,
                    "volume": 120,
                },
            ]

    fetcher = FakeFetcher()
    tool_runner = FinancialToolRunner(
        RuntimeResources(
            llm_service=object(), yf_fetcher=fetcher, upstox_fetcher=FakeUpstox()
        )
    )

    result = await tool_runner.execute("data:fetch_stock_data", {"ticker": "ABC.NS"})

    assert result["success"] is True
    assert result["provenance"]["source"] == "upstox"
    assert result["data"]["period_return_pct"] == 20.0
    assert fetcher.calls == []


@pytest.mark.asyncio
async def test_fundamentals_prefer_upstox_when_an_isin_is_resolved() -> None:
    class FakeUpstox:
        def resolve_instrument(self, ticker: str) -> list[dict]:
            assert ticker == "ABC.NS"
            return [{"isin": "INE000A00000"}]

        def fetch_fundamentals(self, isin: str) -> dict:
            assert isin == "INE000A00000"
            return {"source": "upstox", "peRatio": 12.5, "returnOnEquity": 0.2}

    fetcher = FakeFetcher()
    tool_runner = FinancialToolRunner(
        RuntimeResources(
            llm_service=object(), yf_fetcher=fetcher, upstox_fetcher=FakeUpstox()
        )
    )

    result = await tool_runner.execute("data:fetch_fundamentals", {"ticker": "ABC.NS"})

    assert result["success"] is True
    assert result["data"]["peRatio"] == 12.5
    assert result["provenance"]["source"] == "upstox"
    assert result["provenance"]["quality_status"] == "verified"
    assert fetcher.calls == []


@pytest.mark.asyncio
async def test_news_tool_uses_the_configured_news_pipeline() -> None:
    class FakeNewsPipeline:
        async def run(self, *, company, time_window_days):
            assert company.ticker == "ABC.NS"
            assert time_window_days == 30
            return [
                NewsPipelineRecord(
                    ticker="ABC.NS",
                    company_name="ABC.NS",
                    market="IN",
                    url="https://news.example/article",
                    canonical_url="https://news.example/article",
                    title="ABC update",
                    author=None,
                    snippet="ABC update",
                    article_text="ABC update",
                    word_count=2,
                    publish_time=None,
                    retrieval_time=datetime.now(UTC),
                    source_domain="news.example",
                    source_type="news",
                    source_tier=3,
                    paywall_detected=False,
                    extraction_status="snippet_only",
                    quality_score=42.0,
                    relevance_check=True,
                    is_duplicate=False,
                    cluster_id=None,
                    query_intent="company_news",
                    search_provider="replay",
                    pipeline_version="test",
                )
            ]

    tool_runner = FinancialToolRunner(
        RuntimeResources(
            llm_service=object(),
            yf_fetcher=FakeFetcher(),
            news_pipeline_runner=FakeNewsPipeline(),
        )
    )

    result = await tool_runner.execute("news:fetch_news", {"ticker": "ABC.NS"})

    assert result["success"] is True
    assert result["data"][0]["title"] == "ABC update"
    assert result["sources"] == [
        {"name": "news.example", "url": "https://news.example/article"}
    ]


@pytest.mark.asyncio
async def test_cached_technical_analysis_retains_market_data_provenance() -> None:
    tool_runner, _ = runner()

    await tool_runner.execute("data:fetch_stock_data", {"ticker": "ABC"})
    result = await tool_runner.execute(
        "analysis:get_technical_overview", {"ticker": "ABC"}
    )

    assert result["success"] is True
    assert result["provenance"]["source"] == "yfinance"
    assert result["provenance"]["source_url"] == (
        "https://finance.yahoo.com/quote/ABC/history/"
    )


@pytest.mark.asyncio
async def test_stock_data_archives_the_provider_payload_before_returning_evidence(
    tmp_path,
) -> None:
    fetcher = FakeFetcher()
    tool_runner = FinancialToolRunner(
        RuntimeResources(
            llm_service=object(),
            yf_fetcher=fetcher,
            provider_archive=ProviderArchive(tmp_path),
        )
    )

    result = await tool_runner.execute("data:fetch_stock_data", {"ticker": "ABC"})

    snapshot_hash = result["provenance"]["snapshot_hash"]
    archived = tool_runner.resources.provider_archive.load(snapshot_hash)
    assert archived.operation == "fetch_stock_price"
    assert archived.payload["data"][0]["Close"] == 10


@pytest.mark.asyncio
async def test_unknown_tool_and_missing_ticker_fail_closed() -> None:
    tool_runner, _ = runner()
    unknown = await tool_runner.execute("unknown:tool", {})
    missing = await tool_runner.execute("analysis:run_technical_scan", {})
    assert unknown == {"success": False, "error": "Unknown tool: unknown:tool"}
    assert missing["success"] is False


@pytest.mark.asyncio
async def test_stock_data_blocks_material_vendor_disagreement() -> None:
    class DisagreeingFetcher(FakeFetcher):
        def fetch_stock_price(self, ticker: str, period: str, interval: str) -> dict:
            value = super().fetch_stock_price(ticker, period, interval)
            value["vendor_values"] = {"yfinance": 100.0, "independent": 110.0}
            return value

    fetcher = DisagreeingFetcher()
    tool_runner = FinancialToolRunner(
        RuntimeResources(llm_service=object(), yf_fetcher=fetcher)
    )

    result = await tool_runner.execute("data:fetch_stock_data", {"ticker": "ABC"})

    assert result["success"] is False
    assert result["quality_issues"][0]["code"] == "VENDOR_DISAGREEMENT"
