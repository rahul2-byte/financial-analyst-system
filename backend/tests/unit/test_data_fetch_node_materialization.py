import pytest
from typing import Any
from datetime import UTC, datetime

import agents.financial.data.data_fetch_node as data_fetch_module
from agents.financial.data.data_fetch_node import data_fetch_node
from app.core.node_resources import resources


class _StubSQLDB:
    def __init__(self) -> None:
        self.get_ohlcv_calls: list[tuple[str, Any, Any]] = []
        self.get_fundamentals_info_calls: list[str] = []
        self.cache_status_calls: list[str] = []

    def get_latest_date(self, ticker: str):
        del ticker
        return datetime(2026, 4, 10, tzinfo=UTC)

    def get_ohlcv(self, ticker: str, start_date=None, end_date=None):
        self.get_ohlcv_calls.append((ticker, start_date, end_date))
        return [
            type(
                "Row",
                (),
                {
                    "ticker": ticker,
                    "date": datetime(2026, 4, 9, tzinfo=UTC),
                    "open": 1.0,
                    "high": 2.0,
                    "low": 0.5,
                    "close": 1.5,
                    "volume": 100,
                    "adjusted_close": 1.5,
                },
            )()
        ]

    def get_fundamentals_info(self, ticker: str):
        self.get_fundamentals_info_calls.append(ticker)
        return {
            "ticker": ticker,
            "has_data": True,
            "marketCap": 10,
            "currentPrice": 100,
        }

    def get_cache_status(self, ticker: str):
        self.cache_status_calls.append(ticker)
        if ticker == "MACRO":
            return {"macro": {"extra_info": {"macro_payload": {"NIFTY_50": 22000.0}}}}
        return {}

    def search_instruments_ranked(self, *args, **kwargs):
        del args, kwargs
        return []

    def update_cache_index(self, *args, **kwargs):
        raise AssertionError(
            "update_cache_index should not be called in local-only materialization"
        )


class _StubYFinanceFetcher:
    def fetch_stock_price(self, *args, **kwargs):
        raise AssertionError("online OHLCV fetch should not be called")

    def fetch_company_fundamentals(self, *args, **kwargs):
        raise AssertionError("online fundamentals fetch should not be called")

    def fetch_macro_indicators(self, *args, **kwargs):
        raise AssertionError("online macro fetch should not be called")


class _StubVectorDB:
    def __init__(self, points_by_ticker: dict[str, list[dict[str, Any]]]):
        self.collection_name = "finance_knowledge"
        self._points_by_ticker = {
            k.strip().upper(): v for k, v in (points_by_ticker or {}).items()
        }

    def chunk_and_upsert(self, *args, **kwargs):
        del args, kwargs
        return []

    def list_recent_by_tickers(self, tickers: list[str], limit: int = 20):
        from data.schemas.text import ProcessedChunk

        values = set()
        for t in tickers:
            values.add(t.strip().upper())

        hits = []
        for value in values:
            for payload in self._points_by_ticker.get(value, []):
                hits.append(
                    ProcessedChunk(
                        chunk_id="stub",
                        ticker=payload.get("ticker", value),
                        text=payload.get("text", ""),
                        metadata=payload,
                        embedding=None,
                    )
                )
        return hits[: int(limit)]


@pytest.mark.asyncio
async def test_data_fetch_materializes_all_required_datasets_locally(
    monkeypatch,
) -> None:
    monkeypatch.setattr(resources, "_sql_db", _StubSQLDB())
    monkeypatch.setattr(resources, "_yf_fetcher", _StubYFinanceFetcher())
    monkeypatch.setattr(
        resources,
        "_vector_db",
        _StubVectorDB(
            {
                "AAPL": [
                    {
                        "ticker": "AAPL",
                        "text": "Cached vector news chunk",
                        "source": "pgvector",
                        "published_date": "2026-04-10T00:00:00+00:00",
                        "url": "https://example.com/cached",
                    }
                ]
            }
        ),
    )

    state = {
        "goal": {"ticker": "AAPL"},
        "timeframe_policy": {
            "ohlcv": {"period": "1y", "interval": "1d", "expected_points": 252},
            "news": {"minimum_items": 10},
            "fundamentals": {"required_fields": ["marketCap", "currentPrice"]},
            "macro": {"required_fields": ["NIFTY_50"]},
        },
        "data_status": {
            "ohlcv": {"available": True, "freshness": 1.0, "coverage": 1.0},
            "news": {"available": True, "freshness": 1.0, "coverage": 1.0},
            "fundamentals": {"available": True, "freshness": 1.0, "coverage": 1.0},
            "macro": {"available": True, "freshness": 1.0, "coverage": 1.0},
        },
        "fetched_data": {},
        "data_plan": [],
        "retry_count_by_domain": {},
        "user_query": "test",
        "conversation_history": [],
    }

    result = await data_fetch_node(state)

    fetched = result["fetched_data"]
    assert "ohlcv" in fetched and isinstance(fetched["ohlcv"], dict)
    assert "fundamentals" in fetched and isinstance(fetched["fundamentals"], dict)
    assert (
        "macro" in fetched and isinstance(fetched["macro"], dict) and fetched["macro"]
    )
    assert (
        "news" in fetched
        and isinstance(fetched["news"], list)
        and len(fetched["news"]) == 1
    )

    assert result["retry_count_by_domain"].get("data_fetch", 0) == 0


class _RecordingSQLDB(_StubSQLDB):
    def __init__(self) -> None:
        super().__init__()
        self.cache_updates: list[tuple[str, str, dict[str, Any]]] = []

    def get_cache_status(self, ticker: str):
        self.cache_status_calls.append(ticker)
        return {}

    def update_cache_index(self, ticker: str, dataset: str, extra_info=None):
        self.cache_updates.append((ticker, dataset, dict(extra_info or {})))


@pytest.mark.asyncio
async def test_data_fetch_updates_cache_index_for_news_without_storing_payload(
    monkeypatch,
) -> None:
    import agents.financial.data.data_fetch_node as data_fetch_module

    sql_db = _RecordingSQLDB()
    monkeypatch.setattr(resources, "_sql_db", sql_db)

    async def _stub_fetch_planned_news(**_kwargs):
        return [
            {
                "ticker": "AAPL",
                "title": "Online news",
                "summary": "Online summary",
                "content": "Online content",
                "source": "online",
                "published_date": "2026-04-10T00:00:00+00:00",
                "url": "https://example.com/online",
                "link": "https://example.com/online",
                "fetched_at": "2026-04-10T00:00:00+00:00",
            }
        ]

    monkeypatch.setattr(
        data_fetch_module, "_fetch_planned_news", _stub_fetch_planned_news
    )
    monkeypatch.setattr(
        resources,
        "_vector_db",
        _StubVectorDB({}),
    )

    state = {
        "goal": {"ticker": "AAPL"},
        "timeframe_policy": {"news": {"minimum_items": 1, "stale_after_days": 2}},
        "data_status": {
            "news": {"available": False, "freshness": 0.0, "coverage": 0.0}
        },
        "fetched_data": {},
        "data_plan": [
            {"dataset": "news", "action": "fetch", "requirements": {"minimum_items": 1}}
        ],
        "retry_count_by_domain": {},
        "user_query": "test",
        "conversation_history": [],
    }

    result = await data_fetch_node(state)
    assert isinstance(result["fetched_data"].get("news"), list)

    updates = [u for u in sql_db.cache_updates if u[1] == "news"]
    assert updates, "expected cache_index update for news"
    extra_info = updates[-1][2]
    assert "articles_payload" not in extra_info


@pytest.mark.asyncio
async def test_data_fetch_materializes_news_with_suffix_canonicalization(
    monkeypatch,
) -> None:
    monkeypatch.setattr(resources, "_sql_db", _StubSQLDB())
    monkeypatch.setattr(resources, "_yf_fetcher", _StubYFinanceFetcher())
    monkeypatch.setattr(
        resources,
        "_vector_db",
        _StubVectorDB(
            {
                "RELIANCE": [
                    {
                        "ticker": "RELIANCE",
                        "text": "Reliance news chunk",
                        "source": "pgvector",
                        "published_date": "2026-04-10T00:00:00+00:00",
                        "url": "https://example.com/reliance",
                    }
                ]
            }
        ),
    )

    state = {
        "goal": {"ticker": "RELIANCE.NS"},
        "timeframe_policy": {"news": {"minimum_items": 1, "stale_after_days": 2}},
        "data_status": {"news": {"available": True, "freshness": 1.0, "coverage": 1.0}},
        "fetched_data": {},
        "data_plan": [
            {
                "dataset": "news",
                "action": "materialize",
                "requirements": {"minimum_items": 1},
            }
        ],
        "retry_count_by_domain": {},
        "user_query": "test",
        "conversation_history": [],
    }

    result = await data_fetch_node(state)
    news = result["fetched_data"].get("news")
    assert isinstance(news, list) and news
    assert "Reliance" in str(news[0].get("summary", ""))


@pytest.mark.asyncio
async def test_data_fetch_materializes_news_with_typo_tolerant_resolution(
    monkeypatch,
) -> None:
    class _TypoSQLDB(_StubSQLDB):
        def search_instruments_ranked(self, *args, **kwargs):
            del args
            # Return a confident ranked match
            return [
                {
                    "trading_symbol": "RELIANCE",
                    "score": 0.9,
                },
                {
                    "trading_symbol": "RELAX",
                    "score": 0.6,
                },
            ]

    monkeypatch.setattr(resources, "_sql_db", _TypoSQLDB())
    monkeypatch.setattr(resources, "_yf_fetcher", _StubYFinanceFetcher())
    monkeypatch.setattr(
        resources,
        "_vector_db",
        _StubVectorDB(
            {
                "RELIANCE": [
                    {
                        "ticker": "RELIANCE",
                        "text": "Reliance typo-resolved news chunk",
                        "source": "pgvector",
                        "published_date": "2026-04-10T00:00:00+00:00",
                        "url": "https://example.com/reliance-typo",
                    }
                ]
            }
        ),
    )

    state = {
        "goal": {"ticker": "RELIAANCE"},
        "timeframe_policy": {"news": {"minimum_items": 1, "stale_after_days": 2}},
        "data_status": {"news": {"available": True, "freshness": 1.0, "coverage": 1.0}},
        "fetched_data": {},
        "data_plan": [
            {
                "dataset": "news",
                "action": "materialize",
                "requirements": {"minimum_items": 1},
            }
        ],
        "retry_count_by_domain": {},
        "user_query": "test",
        "conversation_history": [],
    }

    result = await data_fetch_node(state)
    news = result["fetched_data"].get("news")
    assert isinstance(news, list) and news
    assert "typo-resolved" in str(news[0].get("summary", ""))


def test_build_operation_context_merges_requirements_and_falls_back_from_materialize() -> (
    None
):
    state = {
        "data_status": {
            "ohlcv": {"available": True, "freshness": 0.1, "coverage": 0.9}
        },
        "fetched_data": {"ohlcv": {"existing": True}},
        "timeframe": "1y",
        "conversation_history": [{"role": "user", "content": "compare"}],
    }
    item = {
        "dataset": "ohlcv",
        "action": "materialize",
        "requirements": {"expected_points": 252},
    }
    timeframe_policy = {
        "ohlcv": {"period": "1y", "interval": "1d", "minimum_coverage_ratio": 0.8}
    }

    context = data_fetch_module.build_operation_context(
        state=state,
        item=item,
        timeframe_policy=timeframe_policy,
        symbols=["AAPL"],
        ticker="AAPL",
        goal={"ticker": "AAPL"},
        query="compare AAPL",
    )

    assert context["dataset"] == "ohlcv"
    assert context["action"] == "fetch"
    assert context["requirements"] == {
        "period": "1y",
        "interval": "1d",
        "minimum_coverage_ratio": 0.8,
        "expected_points": 252,
    }
    assert context["dataset_state"] == {
        "available": True,
        "freshness": 0.1,
        "coverage": 0.9,
    }
    assert context["dataset_payload"] == {"existing": True}
    assert context["symbols"] == ["AAPL"]
    assert context["ticker"] == "AAPL"
    assert context["timeframe"] == "1y"


def test_apply_dataset_result_updates_state_payload_and_fetch_flag() -> None:
    current_status: dict[str, Any] = {"news": {"available": False}}
    touched_data_status: dict[str, dict[str, Any]] = {}
    fetched_data: dict[str, Any] = {}
    result = {
        "dataset": "news",
        "dataset_state": {},
        "dataset_payload": [{"title": "Online news"}],
        "fetched": [{"title": "Online news"}],
        "available": True,
        "coverage": 1.0,
        "freshness": 0.8,
        "source": "fetch_attempt",
        "error": None,
        "performed_network_fetch": True,
        "should_persist": True,
    }

    performed_network_fetch = data_fetch_module.apply_dataset_result(
        result=result,
        current_status=current_status,
        touched_data_status=touched_data_status,
        fetched_data=fetched_data,
    )

    assert current_status["news"] == {
        "available": True,
        "partial": True,
        "source": "fetch_attempt",
        "coverage": 1.0,
        "freshness": 0.8,
        "error": None,
    }
    assert touched_data_status["news"] == current_status["news"]
    assert fetched_data["news"] == [{"title": "Online news"}]
    assert performed_network_fetch is True
