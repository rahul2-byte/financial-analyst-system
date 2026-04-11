from datetime import UTC, datetime

import pytest

from agents.financial.data import data_fetch_node as data_fetch_module
from agents.financial.data.data_check_node import _merge_local_audit_status
from app.core.node_resources import resources
from app.core.orchestration_schemas import OfflineStatus
from data.providers.news_query_planner import QUERY_SPECS
from data.schemas.text import ProcessedChunk
class _StubSQLDB:
    def __init__(self) -> None:
        self.cache_updates: list[tuple[str, str, dict[str, object]]] = []

    def update_cache_index(self, ticker: str, dataset: str, extra_info=None) -> None:
        self.cache_updates.append((ticker, dataset, dict(extra_info or {})))


class _StubVectorDB:
    def __init__(self) -> None:
        self.upserts: list[list[ProcessedChunk]] = []

    def upsert_chunks(self, chunks) -> None:
        self.upserts.append(list(chunks))


class _StubTextProcessor:
    def __init__(self, use_embeddings: bool = True) -> None:
        self.use_embeddings = use_embeddings

    def process_and_embed(self, text: str, metadata: dict[str, object]):
        return [
            ProcessedChunk(
                chunk_id=f"chunk-{metadata['title_hash']}",
                ticker=str(metadata["ticker"]),
                text=text,
                metadata=metadata,
                embedding=[0.1, 0.2, 0.3],
            )
        ]


class _EmptyChunkTextProcessor:
    def __init__(self, use_embeddings: bool = True) -> None:
        self.use_embeddings = use_embeddings

    def process_and_embed(self, text: str, metadata: dict[str, object]):
        return []


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        fixed = cls(2026, 4, 11, 12, 0, tzinfo=UTC)
        if tz is None:
            return fixed.replace(tzinfo=None)
        return fixed.astimezone(tz)


class _StubWebSearchProvider:
    def search(
        self,
        query: str,
        mode: str = "general",
        max_results: int = 5,
        time_range: str | None = None,
    ):
        return [
            {
                "title": f"Article for {query}",
                "body": "Body",
                "url": "https://news.example.com/story",
                "date": "2026-04-10T11:00:00+00:00",
                "source": "DuckDuckGo",
            }
        ]

    def scrape_webpage(self, url: str) -> str:
        return f"Scraped content for {url}"


class _StubRSSFetcher:
    def fetch_market_news(
        self,
        query: str = "",
        limit: int = 10,
        time_range: str | None = None,
        include_body: bool = False,
        scraper=None,
    ):
        return [
            {
                "title": f"Article for {query}",
                "summary": "Summary",
                "content": "Body",
                "link": "https://news.example.com/story",
                "published": "2026-04-10T11:00:00+00:00",
            }
        ]


class _StubFallbackArticle:
    def model_dump(self, mode: str = "python"):
        return {
            "title": "Fallback article",
            "summary": "Fallback summary",
            "content": "Fallback body",
            "link": "https://finance.example.com/fallback",
            "published_date": "2026-04-11T11:30:00+00:00",
            "source": "Yahoo Finance",
        }


class _StubYFinanceFallbackFetcher:
    def fetch_news(self, ticker: str, limit: int = 10):
        return [_StubFallbackArticle()]


def test_store_data_persists_rich_news_cache_summary_and_chunk_metadata(monkeypatch):
    sql_stub = _StubSQLDB()
    vector_stub = _StubVectorDB()

    monkeypatch.setattr(data_fetch_module, "TextProcessor", _StubTextProcessor)
    monkeypatch.setattr(data_fetch_module.resources, "_sql_db", sql_stub)
    monkeypatch.setattr(data_fetch_module.resources, "_vector_db", vector_stub)

    payload = [
        {
            "ticker": "AAPL",
            "title": "Apple expands enterprise AI",
            "summary": "Apple launched new enterprise AI tooling.",
            "content": "The launch broadens Apple's enterprise AI footprint.",
            "url": "https://news.example.com/apple-ai",
            "canonical_url": "https://news.example.com/apple-ai",
            "published_date": "2026-04-11T11:30:00+00:00",
            "source": "Example News",
            "source_domain": "reuters.com",
            "source_type": "open_web",
            "is_trusted_domain": True,
            "query_variant": "Apple latest company news strategic updates",
            "intent_type": "company_news",
            "timeframe": "7d",
            "fetched_at": "2026-04-11T12:00:00+00:00",
            "dedupe_key": "aapl:article-1",
            "article_hash": "article-1",
            "title_hash": "title-1",
        },
        {
            "ticker": "AAPL",
            "title": "Apple AI duplicate coverage",
            "summary": "A similar article covering the same launch.",
            "content": "Duplicate article body.",
            "url": "https://news.example.com/apple-ai-dup",
            "canonical_url": "https://news.example.com/apple-ai-dup",
            "published_date": "2026-04-11T10:30:00+00:00",
            "source": "Example News",
            "source_domain": "reuters.com",
            "source_type": "open_web",
            "is_trusted_domain": True,
            "query_variant": "Apple latest company news strategic updates",
            "intent_type": "company_news",
            "timeframe": "7d",
            "fetched_at": "2026-04-11T12:00:00+00:00",
            "dedupe_key": "aapl:article-1",
            "article_hash": "article-1",
            "title_hash": "title-2",
        },
        {
            "ticker": "AAPL",
            "title": "Semiconductor regulation shifts",
            "summary": "Sector regulation may reshape supplier economics.",
            "content": "Macro and sector developments continue to evolve.",
            "url": "https://news.example.com/apple-sector",
            "canonical_url": "https://news.example.com/apple-sector",
            "published_date": "2026-04-10T08:00:00+00:00",
            "source": "Sector Desk",
            "source_domain": "industry.example.com",
            "source_type": "open_web",
            "is_trusted_domain": False,
            "query_variant": "Apple sector trends regulation competition macro outlook",
            "intent_type": "macro_sector",
            "timeframe": "7d",
            "fetched_at": "2026-04-11T12:00:00+00:00",
            "dedupe_key": "aapl:article-2",
            "article_hash": "article-2",
            "title_hash": "title-3",
        },
    ]

    data_fetch_module._store_data("news", payload, "AAPL")

    assert len(sql_stub.cache_updates) == 1
    ticker, dataset, extra_info = sql_stub.cache_updates[0]
    assert ticker == "AAPL"
    assert dataset == "news"
    assert extra_info == {
        "last_fetch_at": "2026-04-11T12:00:00+00:00",
        "latest_published_at": "2026-04-11T11:30:00+00:00",
        "article_count": 3,
        "deduped_article_count": 2,
        "trusted_article_count": 2,
        "open_web_article_count": 3,
        "covered_intent_types": ["company_news", "macro_sector"],
        "missing_intent_types": [
            spec["intent_type"]
            for spec in QUERY_SPECS
            if spec["intent_type"] not in {"company_news", "macro_sector"}
        ],
        "query_variants": [
            "Apple latest company news strategic updates",
            "Apple sector trends regulation competition macro outlook",
        ],
        "coverage_by_intent": {
            "company_news": {
                "article_count": 2,
                "deduped_article_count": 1,
                "trusted_article_count": 2,
                "open_web_article_count": 2,
            },
            "macro_sector": {
                "article_count": 1,
                "deduped_article_count": 1,
                "trusted_article_count": 0,
                "open_web_article_count": 1,
            },
        },
        "timeframe": "7d",
        "fresh_enough": True,
        "vector_ready": True,
        "chunk_count": 3,
    }

    assert len(vector_stub.upserts) == 1
    assert len(vector_stub.upserts[0]) == 3
    first_chunk = vector_stub.upserts[0][0]
    assert first_chunk.metadata["intent_type"] == "company_news"
    assert first_chunk.metadata["query_variant"] == "Apple latest company news strategic updates"
    assert first_chunk.metadata["dedupe_key"] == "aapl:article-1"
    assert first_chunk.metadata["canonical_url"] == "https://news.example.com/apple-ai"
    assert first_chunk.metadata["is_trusted_domain"] is True
    assert first_chunk.metadata["timeframe"] == "7d"
    assert first_chunk.metadata["fetched_at"] == "2026-04-11T12:00:00+00:00"


def test_build_news_cache_summary_derives_last_fetch_at_from_payload_metadata() -> None:
    summary = data_fetch_module._build_news_cache_summary(
        [
            {
                "title": "Older fetch",
                "published_date": "2026-04-11T11:30:00+00:00",
                "fetched_at": "2026-04-11T12:00:00+00:00",
                "intent_type": "company_news",
                "query_variant": "alpha",
                "timeframe": "7d",
                "dedupe_key": "a",
                "url": "https://news.example.com/a",
                "source_type": "open_web",
            },
            {
                "title": "Newer fetch",
                "published_date": "2026-04-11T10:30:00+00:00",
                "fetched_at": "2026-04-11T12:05:00+00:00",
                "intent_type": "macro_sector",
                "query_variant": "beta",
                "timeframe": "7d",
                "dedupe_key": "b",
                "url": "https://news.example.com/b",
                "source_type": "open_web",
            },
        ],
        chunk_count=2,
    )

    assert summary["last_fetch_at"] == "2026-04-11T12:05:00+00:00"


def test_store_data_updates_news_cache_summary_even_when_no_chunks_created(monkeypatch):
    sql_stub = _StubSQLDB()
    vector_stub = _StubVectorDB()

    monkeypatch.setattr(data_fetch_module, "TextProcessor", _EmptyChunkTextProcessor)
    monkeypatch.setattr(data_fetch_module.resources, "_sql_db", sql_stub)
    monkeypatch.setattr(data_fetch_module.resources, "_vector_db", vector_stub)

    payload = [
        {
            "ticker": "AAPL",
            "title": "Apple headline only",
            "summary": "",
            "content": "",
            "url": "https://news.example.com/apple-headline",
            "published_date": "2026-04-11T11:30:00+00:00",
            "source_type": "open_web",
            "intent_type": "company_news",
            "query_variant": "Apple latest company news strategic updates",
            "timeframe": "7d",
            "fetched_at": "2026-04-11T12:00:00+00:00",
            "dedupe_key": "headline-only",
        }
    ]

    data_fetch_module._store_data("news", payload, "AAPL")

    assert vector_stub.upserts == []
    assert len(sql_stub.cache_updates) == 1
    _, _, extra_info = sql_stub.cache_updates[0]
    assert extra_info["last_fetch_at"] == "2026-04-11T12:00:00+00:00"
    assert extra_info["chunk_count"] == 0
    assert extra_info["vector_ready"] is False
    assert extra_info["article_count"] == 1


@pytest.mark.asyncio
async def test_data_fetch_node_stamps_fetched_at_on_yfinance_fallback_articles(monkeypatch):
    previous_yf = resources._yf_fetcher
    previous_web = resources._web_search
    previous_sql = resources._sql_db
    previous_vector = resources._vector_db
    try:
        monkeypatch.setattr(data_fetch_module, "datetime", _FixedDateTime)
        monkeypatch.setattr(data_fetch_module.resources, "_yf_fetcher", _StubYFinanceFallbackFetcher())
        monkeypatch.setattr(data_fetch_module.resources, "_web_search", _StubWebSearchProvider())
        monkeypatch.setattr(data_fetch_module.resources, "_sql_db", _StubSQLDB())
        monkeypatch.setattr(data_fetch_module.resources, "_vector_db", _StubVectorDB())

        result = await data_fetch_module.data_fetch_node(
            {
                "goal": {"ticker": "AAPL"},
                "user_query": "Apple latest earnings",
                "data_status": {},
                "data_plan": [{"dataset": "news", "priority": "P0", "action": "fetch"}],
                "retry_count_by_domain": {},
            }
        )
    finally:
        setattr(resources, "_yf_fetcher", previous_yf)
        setattr(resources, "_web_search", previous_web)
        setattr(resources, "_sql_db", previous_sql)
        setattr(resources, "_vector_db", previous_vector)

    fetched_news = result["fetched_data"]["news"]
    assert len(fetched_news) == 1
    assert fetched_news[0]["fetched_at"] == "2026-04-11T12:00:00+00:00"


def test_merge_local_audit_status_derives_news_status():
    offline = OfflineStatus(
        data_available=True,
        ticker_used="AAPL",
        reasoning="Found in cache",
        extra_info={
            "news": {
                "fresh_enough": True,
                "vector_ready": True,
                "covered_intent_types": ["company_news", "earnings", "business_drivers", "macro_sector", "risks_sentiment"],
                "article_count": 10,
                "last_fetch_at": "2026-04-11T12:00:00+00:00",
                "latest_published_at": "2026-04-11T11:00:00+00:00",
            }
        },
    )
    data_status = {}
    timeframe_policy = {"news": {"minimum_coverage_ratio": 0.5}}

    result = _merge_local_audit_status(data_status, "AAPL", offline, timeframe_policy)

    assert result["news"]["available"] is True
    assert result["news"]["freshness"] >= 1.0  # fresh_enough is True
    assert result["news"]["coverage"] >= 1.0
    assert result["news"]["source"] == "cache_index"
    assert result["news"]["error"] is None


def test_merge_local_audit_status_marks_news_unavailable_if_not_fresh():
    offline = OfflineStatus(
        data_available=True,
        ticker_used="AAPL",
        reasoning="Found in cache",
        extra_info={
            "news": {
                "fresh_enough": False,
                "vector_ready": True,
                "covered_intent_types": ["company_news", "earnings", "business_drivers", "macro_sector", "risks_sentiment"],
                "article_count": 10,
            }
        },
    )
    data_status = {}
    result = _merge_local_audit_status(data_status, "AAPL", offline, {})
    assert result["news"]["available"] is False
    assert result["news"]["error"] == "NEWS_STALE"


def test_merge_local_audit_status_marks_news_unavailable_if_not_vector_ready():
    offline = OfflineStatus(
        data_available=True,
        ticker_used="AAPL",
        reasoning="Found in cache",
        extra_info={
            "news": {
                "fresh_enough": True,
                "vector_ready": False,
                "covered_intent_types": ["company_news", "earnings", "business_drivers", "macro_sector", "risks_sentiment"],
                "article_count": 10,
            }
        },
    )
    data_status = {}
    result = _merge_local_audit_status(data_status, "AAPL", offline, {})
    assert result["news"]["available"] is False
    assert result["news"]["error"] == "NEWS_VECTOR_NOT_READY"


from agents.financial.data.data_check_node import data_check_node

def test_merge_local_audit_status_derives_news_coverage_ratio():
    offline = OfflineStatus(
        data_available=True,
        ticker_used="AAPL",
        reasoning="Found in cache",
        extra_info={
            "news": {
                "fresh_enough": True,
                "vector_ready": True,
                "covered_intent_types": ["company_news", "earnings"],  # 2 out of 5
                "article_count": 5,
            }
        },
    )
    data_status = {}
    result = _merge_local_audit_status(data_status, "AAPL", offline, {})
    assert result["news"]["coverage"] == 0.4  # 2/5


@pytest.mark.asyncio
async def test_data_check_node_identifies_stale_news_if_coverage_insufficient(monkeypatch):
    # Mock _run_local_offline_audit to return a status with low coverage
    async def mock_audit(ticker):
        return OfflineStatus(
            data_available=True,
            ticker_used=ticker,
            reasoning="Low coverage",
            extra_info={
                "news": {
                    "fresh_enough": True,
                    "vector_ready": True,
                    "covered_intent_types": ["company_news"], # 0.2 coverage
                    "article_count": 1
                }
            }
        ), []

    import agents.financial.data.data_check_node as dcn_module
    monkeypatch.setattr(dcn_module, "_run_local_offline_audit", mock_audit)

    state = {
        "goal": {"ticker": "AAPL"},
        "data_status": {},
        "timeframe_policy": {
            "news": {"minimum_coverage_ratio": 0.5}
        }
    }

    result = await data_check_node(state)

    assert "news" in result["data_check"]["stale_datasets"]
    assert result["data"]["data_status"]["news"]["coverage"] == 0.2
    assert result["status"] == "partial"
