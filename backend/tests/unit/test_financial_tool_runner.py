from __future__ import annotations

import asyncio
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
    definitions = {
        item["function"]["name"]: item["function"]["parameters"]
        for item in tool_runner.definitions()
    }
    names = set(definitions)
    assert names == {
        "data:fetch_stock_data",
        "data:fetch_fundamentals",
        "news:fetch_news",
        "analysis:run_fundamental_scan",
        "analysis:run_technical_scan",
        "analysis:get_technical_overview",
        "interaction:ask_user",
        "data:fetch_market_status",
        "data:fetch_market_holidays",
    }
    for parameters in definitions.values():
        assert parameters["additionalProperties"] is False
        assert set(parameters["required"]) <= set(parameters["properties"])

    stock = definitions["data:fetch_stock_data"]
    assert stock["properties"]["ticker"]["pattern"] == r"^[A-Za-z0-9._|:-]{1,64}$"
    assert stock["properties"]["period"]["enum"] == [
        "1d",
        "5d",
        "1mo",
        "3mo",
        "6mo",
        "1y",
        "2y",
        "5y",
    ]
    assert stock["properties"]["interval"]["enum"] == [
        "1d",
        "1wk",
        "1h",
        "4h",
        "15m",
        "5m",
        "1m",
    ]
    assert stock["additionalProperties"] is False
    news = definitions["news:fetch_news"]["properties"]["limit"]
    assert (news["minimum"], news["maximum"]) == (1, 20)
    assert definitions["data:fetch_market_status"]["properties"]["exchange"][
        "enum"
    ] == ["NSE", "BSE"]
    assert (
        definitions["data:fetch_market_holidays"]["properties"]["date"]["format"]
        == "date"
    )


@pytest.mark.asyncio
async def test_benchmark_evidence_is_used_without_live_provider_fallback() -> None:
    fetcher = FakeFetcher()
    evidence = {
        "ABC.NS": {
            "success": True,
            "data": {
                "ticker": "ABC.NS",
                "period": "1d",
                "interval": "1d",
                "data": [
                    {
                        "timestamp": "2026-09-22T00:00:00+05:30",
                        "open": 10,
                        "high": 11,
                        "low": 9,
                        "close": 10,
                        "volume": 100,
                    }
                ],
            },
            "provenance": {"source": "upstox", "snapshot_id": "a" * 64},
        },
        "JHS": {
            "success": True,
            "data": {
                "ticker": "JHS",
                "period": "1d",
                "interval": "1d",
                "data": [
                    {
                        "timestamp": "2026-09-22T00:00:00+05:30",
                        "open": 8.54,
                        "high": 8.88,
                        "low": 8.2,
                        "close": 8.25,
                        "volume": 83247,
                    }
                ],
            },
            "provenance": {"source": "upstox", "snapshot_id": "b" * 64},
            "requested_trading_date": "2026-09-22",
        },
        "J&KBANK": {
            "success": True,
            "data": {
                "ticker": "J&KBANK",
                "period": "1d",
                "interval": "1d",
                "data": [
                    {
                        "timestamp": "2026-09-22T00:00:00+05:30",
                        "open": 145,
                        "high": 147,
                        "low": 144,
                        "close": 145.94,
                        "volume": 100,
                    }
                ],
            },
            "provenance": {"source": "upstox", "snapshot_id": "c" * 64},
            "requested_trading_date": "2026-09-22",
        },
    }
    tool_runner = FinancialToolRunner(
        RuntimeResources(llm_service=object(), yf_fetcher=fetcher),
        benchmark_evidence=evidence,
    )

    result = await tool_runner.execute("data:fetch_stock_data", {"ticker": "ABC.NS"})
    alias_result = await tool_runner.execute(
        "data:fetch_stock_data", {"ticker": "JHS.NS"}
    )
    unknown = await tool_runner.execute("data:fetch_stock_data", {"ticker": "OTHER.NS"})
    wrong_exchange = await tool_runner.execute(
        "data:fetch_stock_data", {"ticker": "JHS.BO"}
    )
    punctuation_alias = await tool_runner.execute(
        "data:fetch_stock_data", {"ticker": "JKBANK"}
    )

    assert result["success"] is True
    assert result["data"]["latest"]["close"] == 10
    assert result["provenance"]["snapshot_id"] == "a" * 64
    assert alias_result["success"] is True
    assert alias_result["data"]["latest"]["close"] == 8.25
    assert alias_result["benchmark_context"] == {
        "requested_trading_date": "2026-09-22",
        "date_matches": True,
    }
    evidence["JHS"]["requested_trading_date"] = "2026-09-21"
    mismatched = await tool_runner.execute(
        "data:fetch_stock_data", {"ticker": "JHS.NS"}
    )
    assert mismatched["benchmark_context"]["date_matches"] is False
    assert unknown["success"] is False
    assert "outside the benchmark" in unknown["error"]
    assert wrong_exchange["success"] is False
    assert punctuation_alias["success"] is True
    assert punctuation_alias["data"]["latest"]["close"] == 145.94
    assert fetcher.calls == []


def test_market_status_tool_returns_provider_state_and_provenance() -> None:
    class Upstox:
        def fetch_market_status(self, exchange):
            assert exchange == "NSE"
            return {"exchange": "NSE", "status": "NORMAL_OPEN", "last_updated": 1}

        def fetch_market_holidays(self, date):
            raise AssertionError(date)

    resources = RuntimeResources(
        llm_service=object(), yf_fetcher=FakeFetcher(), upstox_fetcher=Upstox()
    )
    tool_runner = FinancialToolRunner(resources)
    result = asyncio.run(
        tool_runner.execute("data:fetch_market_status", {"exchange": "NSE"})
    )
    assert result["success"] is True
    assert result["data"]["status"] == "NORMAL_OPEN"
    assert result["provenance"]["source"] == "upstox"


def test_fixture_tool_result_overrides_provider_call() -> None:
    tool_runner, _ = runner()
    tool_runner.set_mocked_tools(
        [
            {
                "name": "data:fetch_stock_data",
                "response": {"success": False, "error": "fixture timeout"},
            }
        ]
    )
    result = asyncio.run(
        tool_runner.execute("data:fetch_stock_data", {"ticker": "ABC"})
    )
    assert result == {"success": False, "error": "fixture timeout"}


@pytest.mark.asyncio
async def test_stock_data_returns_summary_and_caches_for_analysis() -> None:
    tool_runner, fetcher = runner()
    result = await tool_runner.execute("data:fetch_stock_data", {"ticker": "ABC"})
    assert result["success"] is True
    assert result["data"]["period_return_pct"] == 20.0
    await tool_runner.execute("analysis:run_technical_scan", {"ticker": "ABC"})
    assert [call[0] for call in fetcher.calls] == ["price"]


@pytest.mark.asyncio
async def test_stock_data_uses_adjusted_close_for_period_return() -> None:
    class AdjustedFetcher(FakeFetcher):
        def fetch_stock_price(self, ticker: str, period: str, interval: str) -> dict:
            return {
                "ticker": ticker,
                "period": period,
                "interval": interval,
                "data": [
                    {
                        "Open": 10,
                        "High": 11,
                        "Low": 9,
                        "Close": 10,
                        "Adj Close": 5,
                        "Volume": 100,
                    },
                    {
                        "Open": 11,
                        "High": 13,
                        "Low": 10,
                        "Close": 12,
                        "Adj Close": 6,
                        "Volume": 120,
                    },
                ],
            }

    fetcher = AdjustedFetcher()
    result = await FinancialToolRunner(
        RuntimeResources(llm_service=object(), yf_fetcher=fetcher)
    ).execute("data:fetch_stock_data", {"ticker": "ABC"})

    assert result["data"]["period_return_pct"] == 20.0
    assert result["data"]["period_return_basis"] == "adjusted_close"
    assert result["data"]["corporate_action_adjusted"] is True


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
async def test_news_tool_uses_cached_company_name_from_fundamentals() -> None:
    class NamedFetcher(FakeFetcher):
        def fetch_company_fundamentals(self, ticker: str) -> dict:
            return {"ticker": ticker, "name": "HDFC Bank Limited", "peRatio": 12}

    class CheckingPipeline:
        async def run(self, *, company, time_window_days):
            assert company.ticker == "HDFCBANK.NS"
            assert company.company_name == "HDFC Bank Limited"
            return []

    tool_runner = FinancialToolRunner(
        RuntimeResources(
            llm_service=object(),
            yf_fetcher=NamedFetcher(),
            news_pipeline_runner=CheckingPipeline(),
        )
    )
    await tool_runner.execute(
        "analysis:run_fundamental_scan", {"ticker": "HDFCBANK.NS"}
    )
    await tool_runner.execute("news:fetch_news", {"ticker": "HDFCBANK.NS"})


@pytest.mark.asyncio
async def test_news_tool_resolves_company_name_from_upstox_when_not_cached() -> None:
    class Upstox:
        def resolve_instrument(self, ticker: str) -> list[dict]:
            assert ticker == "HDFCBANK.NS"
            return [
                {
                    "trading_symbol": "HDFCBANK",
                    "short_name": "HDFC Bank",
                }
            ]

    class CheckingPipeline:
        async def run(self, *, company, time_window_days):
            assert company.company_name == "HDFC Bank"
            return []

    tool_runner = FinancialToolRunner(
        RuntimeResources(
            llm_service=object(),
            yf_fetcher=FakeFetcher(),
            upstox_fetcher=Upstox(),
            news_pipeline_runner=CheckingPipeline(),
        )
    )
    await tool_runner.execute("news:fetch_news", {"ticker": "HDFCBANK.NS"})


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
