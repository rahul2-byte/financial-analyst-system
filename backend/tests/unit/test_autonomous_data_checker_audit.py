import pytest

from agents.financial.data.data_check_node import (
    _run_local_offline_audit,
    data_check_node,
)
from app.core.node_resources import resources


class _ExplodingLLMService:
    def __getattr__(self, name):
        raise AssertionError(
            f"LLM should not be used during deterministic audit: {name}"
        )


class _StubSqlDb:
    def __init__(
        self,
        *,
        exact=None,
        alias=None,
        ranked=None,
        ohlcv=None,
        fundamentals=None,
        macro=None,
        news_cache=None,
    ):
        self._exact = exact or {}
        self._alias = alias or {}
        self._ranked = ranked or {}
        self._ohlcv = ohlcv or {}
        self._fundamentals = fundamentals or {}
        self._macro = macro or {
            "has_data": True,
            "row_count": 12,
            "latest_date": "2026-04-10T00:00:00",
        }
        self._news_cache = news_cache or {}

    def resolve_exact_symbol(self, symbol):
        return self._exact.get(symbol)

    def resolve_alias(self, symbol):
        return self._alias.get(symbol)

    def search_instruments_ranked(
        self, query, limit=10, exchange=None, segment=None, instrument_type=None
    ):
        return list(self._ranked.get(query, []))

    def get_ticker_info(self, ticker):
        return self._ohlcv.get(
            ticker,
            {
                "ticker": ticker,
                "ticker_found": False,
                "has_data": False,
                "row_count": 0,
                "latest_date": None,
            },
        )

    def get_fundamentals_info(self, ticker):
        return self._fundamentals.get(
            ticker,
            {
                "ticker": ticker,
                "ticker_found": False,
                "has_data": False,
                "latest_date": None,
            },
        )

    def get_macro_info(self):
        return dict(self._macro)

    def get_news_cache_info(self, ticker):
        return self._news_cache.get(
            ticker,
            {
                "ticker": ticker,
                "has_data": False,
                "latest_date": None,
                "vector_ready": None,
                "chunk_count": 0,
            },
        )


class _StubVectorDb:
    def __init__(self, by_ticker=None):
        self._by_ticker = by_ticker or {}

    def get_news_info(self, ticker):
        return self._by_ticker.get(
            ticker, {"ticker": ticker, "news_count": 0, "has_news": False}
        )


def _swap_resources(*, sql_db, vector_db, llm_service=None):
    previous = (resources._sql_db, resources._vector_db, resources._llm_service)
    resources._sql_db = sql_db
    resources._vector_db = vector_db
    resources._llm_service = llm_service
    return previous


def _restore_resources(previous):
    resources._sql_db, resources._vector_db, resources._llm_service = previous


@pytest.mark.asyncio
async def test_run_local_offline_audit_resolves_fuzzy_symbol_without_llm() -> None:
    sql_db = _StubSqlDb(
        ranked={
            "APPLE": [
                {
                    "trading_symbol": "AAPL",
                    "company_name": "Apple Inc",
                    "instrument_key": "NSE_EQ|AAPL",
                    "score": 0.92,
                    "match_reason": "trigram_company",
                }
            ]
        },
        ohlcv={
            "AAPL": {
                "ticker": "AAPL",
                "ticker_found": True,
                "has_data": True,
                "row_count": 252,
                "latest_date": "2026-04-10T00:00:00",
            }
        },
        fundamentals={
            "AAPL": {
                "ticker": "AAPL",
                "ticker_found": True,
                "has_data": True,
                "latest_date": "2026-04-09T00:00:00",
                "market_cap": 1,
            }
        },
        news_cache={
            "AAPL": {
                "ticker": "AAPL",
                "has_data": True,
                "latest_date": "2026-04-10T00:00:00",
                "vector_ready": True,
                "chunk_count": 5,
            }
        },
    )
    vector_db = _StubVectorDb(
        {"AAPL": {"ticker": "AAPL", "news_count": 5, "has_news": True}}
    )
    previous = _swap_resources(
        sql_db=sql_db, vector_db=vector_db, llm_service=_ExplodingLLMService()
    )

    try:
        offline, errors = await _run_local_offline_audit("APPLE")
    finally:
        _restore_resources(previous)

    assert errors == []
    assert offline is not None
    assert offline.ticker_used == "AAPL"
    assert offline.data_available is True
    assert "Resolved APPLE to AAPL" in offline.reasoning


@pytest.mark.asyncio
async def test_run_local_offline_audit_marks_ambiguous_symbol_resolution() -> None:
    sql_db = _StubSqlDb(
        ranked={
            "ABC": [
                {
                    "trading_symbol": "ABC1",
                    "company_name": "ABC One",
                    "score": 0.81,
                    "match_reason": "trigram_symbol",
                },
                {
                    "trading_symbol": "ABC2",
                    "company_name": "ABC Two",
                    "score": 0.81,
                    "match_reason": "trigram_symbol",
                },
            ]
        }
    )
    previous = _swap_resources(
        sql_db=sql_db, vector_db=_StubVectorDb(), llm_service=_ExplodingLLMService()
    )

    try:
        offline, errors = await _run_local_offline_audit("ABC")
    finally:
        _restore_resources(previous)

    assert errors == []
    assert offline is not None
    assert offline.ticker_used == "ABC"
    assert offline.data_available is False
    assert offline.ohlcv_data["error"] == "SYMBOL_AMBIGUOUS"
    assert "Could not resolve ABC uniquely" in offline.reasoning


@pytest.mark.asyncio
async def test_run_local_offline_audit_reports_missing_news_reason() -> None:
    sql_db = _StubSqlDb(
        exact={"AAPL": {"trading_symbol": "AAPL", "company_name": "Apple Inc"}},
        ohlcv={
            "AAPL": {
                "ticker": "AAPL",
                "ticker_found": True,
                "has_data": True,
                "row_count": 252,
                "latest_date": "2026-04-10T00:00:00",
            }
        },
        fundamentals={
            "AAPL": {
                "ticker": "AAPL",
                "ticker_found": True,
                "has_data": True,
                "latest_date": "2026-04-09T00:00:00",
                "market_cap": 1,
            }
        },
        news_cache={
            "AAPL": {
                "ticker": "AAPL",
                "has_data": True,
                "latest_date": "2026-04-10T00:00:00",
                "vector_ready": False,
                "chunk_count": 0,
            }
        },
    )
    vector_db = _StubVectorDb(
        {"AAPL": {"ticker": "AAPL", "news_count": 0, "has_news": False}}
    )
    previous = _swap_resources(
        sql_db=sql_db, vector_db=vector_db, llm_service=_ExplodingLLMService()
    )

    try:
        offline, errors = await _run_local_offline_audit("AAPL")
    finally:
        _restore_resources(previous)

    assert errors == []
    assert offline is not None
    assert offline.data_available is False
    assert offline.news_data["error"] == "NEWS_VECTOR_NOT_READY"


@pytest.mark.asyncio
async def test_run_local_offline_audit_handles_nondict_dataset_payloads() -> None:
    class _BrokenSqlDb(_StubSqlDb):
        def get_ticker_info(self, ticker):
            return None

        def get_fundamentals_info(self, ticker):
            return "bad-payload"

    sql_db = _BrokenSqlDb(exact={"AAPL": {"trading_symbol": "AAPL"}})
    previous = _swap_resources(
        sql_db=sql_db,
        vector_db=_StubVectorDb({"AAPL": {"has_news": True, "news_count": 2}}),
        llm_service=_ExplodingLLMService(),
    )

    try:
        offline, errors = await _run_local_offline_audit("AAPL")
    finally:
        _restore_resources(previous)

    assert errors == []
    assert offline is not None
    assert offline.ticker_used == "AAPL"
    assert offline.ohlcv_data["has_data"] is False
    assert offline.fundamentals_data["has_data"] is False


@pytest.mark.asyncio
async def test_data_check_node_uses_deterministic_audit_to_update_goal_ticker() -> None:
    sql_db = _StubSqlDb(
        ranked={
            "APPLE": [
                {
                    "trading_symbol": "AAPL",
                    "company_name": "Apple Inc",
                    "instrument_key": "NSE_EQ|AAPL",
                    "score": 0.92,
                    "match_reason": "trigram_company",
                }
            ]
        },
        ohlcv={
            "AAPL": {
                "ticker": "AAPL",
                "ticker_found": True,
                "has_data": True,
                "row_count": 252,
                "latest_date": "2026-04-10T00:00:00",
            }
        },
        fundamentals={
            "AAPL": {
                "ticker": "AAPL",
                "ticker_found": True,
                "has_data": True,
                "latest_date": "2026-04-09T00:00:00",
                "market_cap": 1,
            }
        },
        news_cache={
            "AAPL": {
                "ticker": "AAPL",
                "has_data": True,
                "latest_date": "2026-04-10T00:00:00",
                "vector_ready": True,
                "chunk_count": 5,
            }
        },
    )
    vector_db = _StubVectorDb(
        {"AAPL": {"ticker": "AAPL", "news_count": 5, "has_news": True}}
    )
    previous = _swap_resources(
        sql_db=sql_db, vector_db=vector_db, llm_service=_ExplodingLLMService()
    )

    try:
        result = await data_check_node(
            {
                "user_query": "Analyze Apple",
                "goal": {"ticker": "APPLE"},
                "data_status": {},
            }
        )
    finally:
        _restore_resources(previous)

    assert result["goal"]["ticker"] == "AAPL"
    assert result["goal"]["ticker_resolution_source"] == "offline_audit"
    assert result["data_check"]["local_audit"]["resolved_ticker"] == "AAPL"
    assert result["data_status"]["ohlcv"]["available"] is True
    assert result["data_status"]["fundamentals"]["available"] is True
    assert result["data_status"]["news"]["available"] is True
    assert result["data_status"]["macro"]["available"] is True


@pytest.mark.asyncio
async def test_data_check_node_surfaces_offline_audit_failures(monkeypatch) -> None:
    async def _boom(_ticker: str):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(
        "agents.financial.data.data_check_node._run_local_offline_audit", _boom
    )

    result = await data_check_node(
        {
            "goal": {"ticker": "AAPL"},
            "data_status": {},
        }
    )

    assert result["status"] == "partial"
    assert result["errors"] == ["offline_audit_error: db unavailable"]
