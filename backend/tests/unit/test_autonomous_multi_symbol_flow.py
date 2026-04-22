import pytest
from typing import Any
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import agents.financial.data.data_fetch_node as data_fetch_module
from agents.financial.data.data_fetch_node import data_fetch_node
from agents.financial.research.research_plan_node import research_plan_node
from app.core.node_resources import resources


class _StubNewsPipelineRunner:
    def __init__(self, records):
        self.records = records
        self.calls: list[dict[str, Any]] = []

    async def run(self, *, company, time_window_days):
        self.calls.append({"company": company, "time_window_days": time_window_days})
        return list(self.records)


def _pipeline_record(
    title: str, *, ticker: str = "AAPL", source_domain: str = "bseindia.com"
):
    from data.news_pipeline.models import NewsPipelineRecord

    now = datetime.now(UTC) - timedelta(hours=1)
    return NewsPipelineRecord(
        ticker=ticker,
        company_name=ticker,
        market="IN",
        url=f"https://{source_domain}/{title.replace(' ', '-').lower()}",
        canonical_url=f"https://{source_domain}/{title.replace(' ', '-').lower()}",
        title=title,
        author=None,
        snippet=f"Snippet for {title}",
        article_text=f"{ticker} detailed article body " * 30,
        word_count=120,
        publish_time=now,
        retrieval_time=now,
        source_domain=source_domain,
        source_type="filing",
        source_tier=1,
        paywall_detected=False,
        extraction_status="full",
        quality_score=80,
        relevance_check=True,
        is_duplicate=False,
        cluster_id=title,
        query_intent="earnings",
        search_provider="bse",
        pipeline_version="1.0.0",
    )


class _StubYFinanceFetcher:
    def __init__(self) -> None:
        self.price_calls: list[tuple[str, str, str]] = []

    def fetch_stock_price(self, ticker: str, period: str = "1mo", interval: str = "1d"):
        self.price_calls.append((ticker, period, interval))
        if ticker == "AAPL":
            return {
                "ticker": ticker,
                "period": period,
                "interval": interval,
                "data": [{"Date": "2026-04-02"}],
            }
        return {
            "ticker": ticker,
            "period": period,
            "interval": interval,
            "data": [{"Date": "2026-03-15"}],
        }

    def fetch_company_fundamentals(self, ticker: str):
        if ticker == "AAPL":
            return {
                "ticker": ticker,
                "marketCap": 10,
                "currentPrice": 100,
                "trailingPE": 20,
                "forwardPE": 18,
                "returnOnEquity": 0.18,
                "debtToEquity": 0.4,
                "revenueGrowth": 0.1,
                "earningsGrowth": 0.08,
            }
        return {
            "ticker": ticker,
            "marketCap": 5,
            "currentPrice": 50,
            "trailingPE": 15,
            "forwardPE": 14,
        }

    def fetch_macro_indicators(self):
        return {
            "NIFTY_50": 22000.0,
            "INDIA_VIX": 12.0,
            "USD_INR": 83.1,
            "CRUDE_OIL": 81.0,
            "GOLD": 2300.0,
        }


class _StubRSSFetcher:
    def __init__(self, articles=None):
        self.calls: list[dict[str, object]] = []
        self.articles = articles

    def fetch_market_news(
        self,
        query: str = "",
        limit: int = 20,
        time_range: str | None = None,
        include_body: bool = False,
        scraper=None,
    ):
        self.calls.append(
            {
                "query": query,
                "limit": limit,
                "time_range": time_range,
                "include_body": include_body,
                "scraper": scraper,
            }
        )
        recent = datetime.now(UTC) - timedelta(hours=1)
        older = datetime.now(UTC) - timedelta(days=3)
        articles = self.articles or [
            {
                "title": f"Older news for {query}",
                "summary": f"Older summary for {query}",
                "content": f"Older content for {query}",
                "link": "https://example.com/older",
                "published": format_datetime(older),
            },
            {
                "title": f"Recent news for {query}",
                "summary": f"Recent summary for {query}",
                "content": f"Recent content for {query}",
                "link": "https://example.com/recent",
                "published": format_datetime(recent),
            },
        ]
        return articles[:limit]


class _StubNewsArticle:
    def __init__(self, ticker: str, published_date: datetime) -> None:
        self.ticker = ticker
        self.published_date = published_date

    def model_dump(self, mode: str = "python"):
        return {
            "title": f"Fallback article for {self.ticker}",
            "summary": f"Fallback summary for {self.ticker}",
            "link": "https://example.com/fallback",
            "published_date": (
                self.published_date.isoformat()
                if mode == "json"
                else self.published_date
            ),
            "source": "Yahoo Finance",
            "content": f"fallback content for {self.ticker}",
        }


class _StubYFinanceNewsFetcher(_StubYFinanceFetcher):
    def __init__(self) -> None:
        super().__init__()
        self.news_calls: list[tuple[str, int]] = []

    def fetch_news(self, ticker: str, limit: int = 10):
        self.news_calls.append((ticker, limit))
        return [_StubNewsArticle(ticker, datetime.now(UTC) - timedelta(minutes=30))]


class _StubSQLDB:
    def __init__(self) -> None:
        self.saved_ohlcv: list[list[object]] = []
        self.fundamentals_payloads: list[dict[str, object]] = []
        self.cache_updates: list[tuple[str, str, dict[str, object]]] = []

    def save_ohlcv(self, rows):
        self.saved_ohlcv.append(list(rows))

    def upsert_fundamentals(self, payload):
        self.fundamentals_payloads.append(dict(payload))

    def update_cache_index(self, ticker: str, dataset: str, extra_info=None):
        self.cache_updates.append((ticker, dataset, dict(extra_info or {})))


class _StubVectorDB:
    def upsert_chunks(self, chunks):
        return None

    def chunk_and_upsert(self, text: str, metadata: dict):
        return []


@pytest.mark.asyncio
async def test_research_planner_uses_goal_instruments_as_symbols() -> None:
    result = await research_plan_node(
        {
            "user_query": "Compare AAPL and MSFT",
            "goal": {
                "ticker": "AAPL",
                "instruments": [
                    {"trading_symbol": "AAPL"},
                    {"trading_symbol": "MSFT"},
                ],
            },
        }
    )

    tasks = result["tasks"]
    assert tasks
    # Deep research runs on the primary ticker only.
    assert tasks[0]["parameters"]["symbols"] == ["AAPL"]
    assert tasks[0]["parameters"]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_data_fetch_node_fetches_ohlcv_for_all_goal_symbols() -> None:
    previous = resources._yf_fetcher
    stub = _StubYFinanceFetcher()
    setattr(resources, "_yf_fetcher", stub)
    try:
        result = await data_fetch_node(
            {
                "goal": {
                    "ticker": "AAPL",
                    "instruments": [
                        {"trading_symbol": "AAPL"},
                        {"trading_symbol": "MSFT"},
                    ],
                },
                "user_query": "Compare AAPL and MSFT",
                "data_status": {},
                "timeframe_policy": {
                    "ohlcv": {
                        "period": "5y",
                        "interval": "1d",
                        "expected_points": 1260,
                        "minimum_coverage_ratio": 0.8,
                        "stale_after_days": 5,
                    }
                },
                "data_plan": [
                    {
                        "dataset": "ohlcv",
                        "priority": "P0",
                        "action": "fetch",
                        "requirements": {
                            "period": "5y",
                            "interval": "1d",
                            "expected_points": 1260,
                            "minimum_coverage_ratio": 0.8,
                            "stale_after_days": 5,
                        },
                    }
                ],
                "retry_count_by_domain": {},
                "timeouts": {"task_timeout_s": 10.0, "stage_timeout_s": 20.0},
            }
        )
    finally:
        setattr(resources, "_yf_fetcher", previous)

    # data_fetch_node only fetches the primary ticker.
    assert stub.price_calls == [("AAPL", "5y", "1d")]
    dataset = result["data_status"]["ohlcv"]
    assert dataset["available"] is True
    assert set(dataset["by_symbol"].keys()) == {"AAPL"}
    assert dataset["coverage"] < 0.1


@pytest.mark.asyncio
async def test_data_fetch_node_preserves_aggregate_metrics_from_by_symbol_data() -> (
    None
):
    previous = resources._yf_fetcher
    stub = _StubYFinanceFetcher()
    setattr(resources, "_yf_fetcher", stub)
    try:
        result = await data_fetch_node(
            {
                "goal": {
                    "ticker": "AAPL",
                    "instruments": [
                        {"trading_symbol": "AAPL"},
                        {"trading_symbol": "MSFT"},
                    ],
                },
                "user_query": "Compare AAPL and MSFT",
                "data_status": {},
                "data_plan": [
                    {"dataset": "ohlcv", "priority": "P0", "action": "fetch"},
                    {
                        "dataset": "fundamentals",
                        "priority": "P1",
                        "action": "fetch",
                    },
                ],
                "retry_count_by_domain": {},
                "timeouts": {"task_timeout_s": 10.0, "stage_timeout_s": 20.0},
            }
        )
    finally:
        setattr(resources, "_yf_fetcher", previous)

    ohlcv = result["data_status"]["ohlcv"]
    ohlcv_symbol_freshness = min(
        detail["freshness"] for detail in ohlcv["by_symbol"].values()
    )
    ohlcv_symbol_coverage = min(
        detail["coverage"] for detail in ohlcv["by_symbol"].values()
    )
    assert ohlcv["freshness"] == ohlcv_symbol_freshness
    assert ohlcv["coverage"] == ohlcv_symbol_coverage

    fundamentals = result["data_status"]["fundamentals"]
    fundamentals_symbol_freshness = min(
        detail["freshness"] for detail in fundamentals["by_symbol"].values()
    )
    fundamentals_symbol_coverage = min(
        detail["coverage"] for detail in fundamentals["by_symbol"].values()
    )
    assert fundamentals["freshness"] == fundamentals_symbol_freshness
    assert fundamentals["coverage"] == fundamentals_symbol_coverage


@pytest.mark.asyncio
async def test_data_fetch_node_persists_multi_symbol_ohlcv_and_fundamentals() -> None:
    previous_yf = resources._yf_fetcher
    previous_sql = resources._sql_db
    previous_vector = resources._vector_db
    sql_stub = _StubSQLDB()
    setattr(resources, "_yf_fetcher", _StubYFinanceFetcher())
    setattr(resources, "_sql_db", sql_stub)
    setattr(resources, "_vector_db", _StubVectorDB())
    try:
        await data_fetch_node(
            {
                "goal": {
                    "ticker": "AAPL",
                    "instruments": [
                        {"trading_symbol": "AAPL"},
                        {"trading_symbol": "MSFT"},
                    ],
                },
                "user_query": "Compare AAPL and MSFT",
                "data_status": {},
                "data_plan": [
                    {"dataset": "ohlcv", "priority": "P0", "action": "fetch"},
                    {
                        "dataset": "fundamentals",
                        "priority": "P1",
                        "action": "fetch",
                    },
                ],
                "retry_count_by_domain": {},
            }
        )
    finally:
        setattr(resources, "_yf_fetcher", previous_yf)
        setattr(resources, "_sql_db", previous_sql)
        setattr(resources, "_vector_db", previous_vector)

    assert len(sql_stub.saved_ohlcv) == 1
    assert [getattr(rows[0], "ticker") for rows in sql_stub.saved_ohlcv] == ["AAPL"]
    assert [payload["ticker"] for payload in sql_stub.fundamentals_payloads] == ["AAPL"]


@pytest.mark.asyncio
async def test_data_fetch_node_updates_freshness_for_provider_payload_shapes(
    monkeypatch,
) -> None:
    previous_yf = resources._yf_fetcher
    setattr(resources, "_yf_fetcher", _StubYFinanceFetcher())
    runner = _StubNewsPipelineRunner([_pipeline_record("Fresh Article")])
    monkeypatch.setattr(
        data_fetch_module, "_build_news_pipeline_runner", lambda: runner
    )
    try:
        result = await data_fetch_node(
            {
                "goal": {"ticker": "AAPL"},
                "user_query": "Analyze AAPL",
                "data_status": {},
                "data_plan": [
                    {"dataset": "news", "priority": "P0", "action": "fetch"},
                    {
                        "dataset": "fundamentals",
                        "priority": "P1",
                        "action": "fetch",
                        "requirements": {"stale_after_days": 90},
                    },
                    {"dataset": "macro", "priority": "P1", "action": "fetch"},
                ],
                "retry_count_by_domain": {},
                "timeouts": {"task_timeout_s": 10.0, "stage_timeout_s": 20.0},
            }
        )
    finally:
        setattr(resources, "_yf_fetcher", previous_yf)

    assert result["data_status"]["news"]["freshness"] > 0.9
    assert result["data_status"]["fundamentals"]["freshness"] > 0.9
    assert result["data_status"]["macro"]["freshness"] > 0.9


@pytest.mark.asyncio
async def test_data_fetch_node_uses_dataset_specific_coverage_rules(
    monkeypatch,
) -> None:
    previous_yf = resources._yf_fetcher
    setattr(resources, "_yf_fetcher", _StubYFinanceFetcher())
    runner = _StubNewsPipelineRunner([_pipeline_record("Coverage Article")])
    monkeypatch.setattr(
        data_fetch_module, "_build_news_pipeline_runner", lambda: runner
    )
    try:
        result = await data_fetch_node(
            {
                "goal": {
                    "ticker": "AAPL",
                    "instruments": [
                        {"trading_symbol": "AAPL"},
                        {"trading_symbol": "MSFT"},
                    ],
                },
                "user_query": "Analyze AAPL",
                "data_status": {},
                "timeframe_policy": {
                    "news": {"minimum_items": 10, "stale_after_days": 2},
                    "fundamentals": {
                        "required_fields": [
                            "marketCap",
                            "currentPrice",
                            "trailingPE",
                            "forwardPE",
                            "returnOnEquity",
                            "debtToEquity",
                            "revenueGrowth",
                            "earningsGrowth",
                        ],
                        "stale_after_days": 90,
                    },
                    "macro": {
                        "required_fields": [
                            "NIFTY_50",
                            "INDIA_VIX",
                            "USD_INR",
                            "CRUDE_OIL",
                            "GOLD",
                        ],
                        "stale_after_days": 7,
                    },
                },
                "data_plan": [
                    {
                        "dataset": "news",
                        "priority": "P0",
                        "action": "fetch",
                        "requirements": {"minimum_items": 10, "stale_after_days": 2},
                    },
                    {
                        "dataset": "fundamentals",
                        "priority": "P1",
                        "action": "fetch",
                        "requirements": {
                            "required_fields": [
                                "marketCap",
                                "currentPrice",
                                "trailingPE",
                                "forwardPE",
                                "returnOnEquity",
                                "debtToEquity",
                                "revenueGrowth",
                                "earningsGrowth",
                            ],
                            "stale_after_days": 90,
                        },
                    },
                    {
                        "dataset": "macro",
                        "priority": "P1",
                        "action": "fetch",
                        "requirements": {
                            "required_fields": [
                                "NIFTY_50",
                                "INDIA_VIX",
                                "USD_INR",
                                "CRUDE_OIL",
                                "GOLD",
                            ],
                            "stale_after_days": 7,
                        },
                    },
                ],
                "retry_count_by_domain": {},
            }
        )
    finally:
        setattr(resources, "_yf_fetcher", previous_yf)

    assert result["data_status"]["news"]["coverage"] == 0.1
    assert result["data_status"]["macro"]["coverage"] == 1.0
    assert result["data_status"]["fundamentals"]["coverage"] == 0.5333


@pytest.mark.asyncio
async def test_data_fetch_node_falls_back_to_timeframe_policy_when_requirements_missing(
    monkeypatch,
) -> None:
    previous_yf = resources._yf_fetcher
    setattr(resources, "_yf_fetcher", _StubYFinanceFetcher())
    runner = _StubNewsPipelineRunner([_pipeline_record("Policy Fallback Article")])
    monkeypatch.setattr(
        data_fetch_module, "_build_news_pipeline_runner", lambda: runner
    )
    try:
        result = await data_fetch_node(
            {
                "goal": {
                    "ticker": "AAPL",
                    "instruments": [{"trading_symbol": "AAPL"}],
                },
                "user_query": "Analyze AAPL",
                "data_status": {},
                "timeframe_policy": {
                    "news": {"minimum_items": 10, "stale_after_days": 2},
                    "fundamentals": {
                        "required_fields": [
                            "marketCap",
                            "currentPrice",
                            "trailingPE",
                            "forwardPE",
                            "returnOnEquity",
                            "debtToEquity",
                            "revenueGrowth",
                            "earningsGrowth",
                        ],
                        "stale_after_days": 90,
                    },
                    "macro": {
                        "required_fields": [
                            "NIFTY_50",
                            "INDIA_VIX",
                            "USD_INR",
                            "CRUDE_OIL",
                            "GOLD",
                        ],
                        "stale_after_days": 7,
                    },
                },
                "data_plan": [
                    {"dataset": "news", "priority": "P0", "action": "fetch"},
                    {
                        "dataset": "fundamentals",
                        "priority": "P1",
                        "action": "fetch",
                    },
                    {"dataset": "macro", "priority": "P1", "action": "fetch"},
                ],
                "retry_count_by_domain": {},
            }
        )
    finally:
        setattr(resources, "_yf_fetcher", previous_yf)

    assert result["data_status"]["news"]["coverage"] == 0.1
    assert result["data_status"]["macro"]["coverage"] == 1.0
    assert result["data_status"]["fundamentals"]["coverage"] > 0.0


@pytest.mark.asyncio
async def test_data_fetch_node_uses_news_pipeline_runner_without_us_fallback(
    monkeypatch,
) -> None:
    previous_yf = resources._yf_fetcher
    runner = _StubNewsPipelineRunner(
        [_pipeline_record("Runner Article", ticker="HDFCBANK")]
    )

    monkeypatch.setattr(
        data_fetch_module, "_build_news_pipeline_runner", lambda: runner
    )

    setattr(resources, "_yf_fetcher", _StubYFinanceFetcher())
    try:
        result = await data_fetch_node(
            {
                "goal": {"ticker": "HDFCBANK"},
                "user_query": "HDFC Bank latest earnings",
                "data_status": {},
                "data_plan": [
                    {"dataset": "news", "priority": "P0", "action": "fetch"},
                ],
                "retry_count_by_domain": {},
                "timeouts": {"task_timeout_s": 10.0, "stage_timeout_s": 20.0},
            }
        )
    finally:
        setattr(resources, "_yf_fetcher", previous_yf)

    assert runner.calls[0]["company"].ticker == "HDFCBANK"
    assert result["data_status"]["news"]["freshness"] > 0.9
    assert result["data_status"]["news"]["source"] == "fetch_attempt"


@pytest.mark.asyncio
async def test_data_fetch_node_calls_news_pipeline_runner_with_timeframe(
    monkeypatch,
) -> None:
    previous_yf = resources._yf_fetcher
    runner = _StubNewsPipelineRunner(
        [_pipeline_record("Timeframe Article", ticker="HDFCBANK")]
    )
    setattr(resources, "_yf_fetcher", _StubYFinanceFetcher())

    goal = {"ticker": "HDFCBANK", "objective": "Analyse the HDFC stock"}
    user_query = "Timeframe: 1 year Scope full stock analysis"
    monkeypatch.setattr(
        data_fetch_module, "_build_news_pipeline_runner", lambda: runner
    )
    try:
        await data_fetch_node(
            {
                "goal": goal,
                "user_query": user_query,
                "timeframe": "1 year",
                "data_status": {},
                "timeframe_policy": {
                    "news": {"minimum_items": 10, "stale_after_days": 2}
                },
                "data_plan": [
                    {
                        "dataset": "news",
                        "priority": "P0",
                        "action": "fetch",
                        "requirements": {"minimum_items": 10, "stale_after_days": 2},
                    }
                ],
                "retry_count_by_domain": {},
            }
        )
    finally:
        setattr(resources, "_yf_fetcher", previous_yf)

    assert runner.calls[0]["company"].ticker == "HDFCBANK"
    assert runner.calls[0]["time_window_days"] == 30
