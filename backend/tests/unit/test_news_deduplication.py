from datetime import UTC, datetime

from data.processors.text import TextProcessor
from data.providers.rss_news import (
    RSSNewsFetcher,
    deduplicate_articles,
    derive_article_hash,
    enrich_article_with_body,
    normalize_article_url,
)
from data.schemas.text import NewsArticle


def test_news_article_accepts_rich_metadata_fields():
    published_at = datetime(2026, 4, 10, 12, 30, tzinfo=UTC)
    fetched_at = datetime(2026, 4, 10, 12, 45, tzinfo=UTC)

    article = NewsArticle(
        ticker="AAPL",
        title="Apple expands AI tooling",
        url="https://news.example.com/apple-ai",
        source="Example News",
        published_date=published_at,
        summary="Apple expanded its enterprise AI tooling.",
        content="Full article text",
        company_name="Apple Inc.",
        query_objective="latest_company_news",
        query_variant="apple earnings ai",
        intent_type="news",
        search_rank=1,
        search_provider="serper",
        source_domain="news.example.com",
        source_type="news",
        source_priority=10,
        original_url="https://news.example.com/apple-ai?utm_source=feed",
        canonical_url="https://news.example.com/apple-ai",
        resolved_url="https://news.example.com/apple-ai",
        fetched_at=fetched_at,
        language="en",
        content_hash="content-hash",
        title_hash="title-hash",
        article_hash="article-hash",
        is_trusted_domain=True,
        dedupe_key="aapl:article-hash",
        timeframe="7d",
        run_id="run-123",
    )

    assert article.company_name == "Apple Inc."
    assert article.search_rank == 1
    assert article.is_trusted_domain is True
    assert article.fetched_at == fetched_at
    assert article.dedupe_key == "aapl:article-hash"


def test_text_processor_preserves_rich_metadata_for_chunks():
    processor = TextProcessor(chunk_size=200, chunk_overlap=20, use_embeddings=False)
    fetched_at = datetime(2026, 4, 10, 12, 45, tzinfo=UTC)

    chunks = processor.chunk_text(
        "Apple released a detailed platform update for enterprise customers.",
        metadata={
            "ticker": "AAPL",
            "dedupe_key": "aapl:article-hash",
            "article_hash": "article-hash",
            "title_hash": "title-hash",
            "content_hash": "content-hash",
            "is_trusted_domain": True,
            "fetched_at": fetched_at,
            "canonical_url": "https://news.example.com/apple-ai",
        },
    )

    assert len(chunks) == 1
    assert chunks[0].ticker == "AAPL"
    assert chunks[0].metadata["dedupe_key"] == "aapl:article-hash"
    assert chunks[0].metadata["article_hash"] == "article-hash"
    assert chunks[0].metadata["title_hash"] == "title-hash"
    assert chunks[0].metadata["content_hash"] == "content-hash"
    assert chunks[0].metadata["is_trusted_domain"] is True
    assert chunks[0].metadata["fetched_at"] == fetched_at.isoformat()
    assert chunks[0].metadata["canonical_url"] == "https://news.example.com/apple-ai"


def test_text_processor_rejects_unsupported_metadata_values():
    processor = TextProcessor(chunk_size=200, chunk_overlap=20, use_embeddings=False)

    try:
        processor.chunk_text(
            "Apple released a detailed platform update for enterprise customers.",
            metadata={"ticker": "AAPL", "unsupported": ["nested", "value"]},
        )
    except TypeError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("Expected unsupported metadata values to fail fast")


def test_text_processor_requires_ticker_metadata():
    processor = TextProcessor(chunk_size=200, chunk_overlap=20, use_embeddings=False)

    try:
        processor.chunk_text(
            "Apple released a detailed platform update for enterprise customers.",
            metadata={"canonical_url": "https://news.example.com/apple-ai"},
        )
    except ValueError as exc:
        assert "ticker" in str(exc)
    else:
        raise AssertionError("Expected ticker metadata to be required")


def test_deduplicate_articles_removes_exact_duplicate_canonical_urls():
    articles = [
        {
            "title": "Markets rise",
            "link": "https://news.example.com/story?utm_source=rss",
            "canonical_url": "https://news.example.com/story",
            "summary": "Stocks moved higher.",
        },
        {
            "title": "Markets rise duplicate",
            "link": "https://news.example.com/story?utm_source=email",
            "canonical_url": "https://news.example.com/story",
            "summary": "Duplicate copy.",
        },
    ]

    deduped = deduplicate_articles(articles)

    assert len(deduped) == 1
    assert deduped[0]["canonical_url"] == "https://news.example.com/story"


def test_deduplicate_articles_removes_exact_duplicate_article_hashes():
    article_hash = derive_article_hash("Markets rise", "Stocks moved higher.")
    articles = [
        {
            "title": "Markets rise",
            "link": "https://news.example.com/story-1",
            "summary": "Stocks moved higher.",
            "article_hash": article_hash,
        },
        {
            "title": "Markets rise",
            "link": "https://news.example.com/story-2",
            "summary": "Stocks moved higher.",
            "article_hash": article_hash,
        },
    ]

    deduped = deduplicate_articles(articles)

    assert len(deduped) == 1
    assert deduped[0]["article_hash"] == article_hash


def test_enrich_article_with_body_uses_scraper_text():
    class StubScraper:
        def scrape_webpage(self, url: str) -> str:
            assert url == "https://news.example.com/story"
            return "Full cleaned article body"

    article = {
        "title": "Markets rise",
        "link": "https://news.example.com/story",
        "summary": "Short summary",
    }

    enriched = enrich_article_with_body(article, StubScraper())

    assert enriched["content"] == "Full cleaned article body"
    assert enriched["summary"] == "Short summary"


def test_fetch_market_news_keeps_category_feed_behavior_and_deduplicates(monkeypatch):
    fetcher = RSSNewsFetcher()

    class ParsedFeed:
        entries = [
            {
                "title": "Markets rise",
                "summary": "Stocks moved higher.",
                "link": "https://news.example.com/story?utm_source=rss",
                "published": "2026-04-11",
            },
            {
                "title": "Markets rise duplicate",
                "summary": "Duplicate story.",
                "link": "https://news.example.com/story?utm_source=email",
                "published": "2026-04-11",
            },
        ]

    def fake_parse(url: str):
        assert url == RSSNewsFetcher.FEEDS["markets"]
        return ParsedFeed()

    monkeypatch.setattr("data.providers.rss_news.feedparser.parse", fake_parse)

    results = fetcher.fetch_market_news("markets")

    assert len(results) == 1
    assert results[0]["canonical_url"] == "https://news.example.com/story"
    assert results[0]["link"] == "https://news.example.com/story?utm_source=rss"


def test_normalize_article_url_sorts_equivalent_query_params():
    normalized_a = normalize_article_url("https://news.example.com/story?b=2&a=1")
    normalized_b = normalize_article_url("https://news.example.com/story?a=1&b=2")

    assert normalized_a == "https://news.example.com/story?a=1&b=2"
    assert normalized_a == normalized_b


def test_fetch_market_news_deduplicates_again_after_body_enrichment(monkeypatch):
    fetcher = RSSNewsFetcher()

    class ParsedFeed:
        entries = [
            {
                "title": "Markets rise",
                "summary": "Short one.",
                "link": "https://news.example.com/story-1",
                "published": "2026-04-11",
            },
            {
                "title": "Markets rise",
                "summary": "Short two.",
                "link": "https://news.example.com/story-2",
                "published": "2026-04-11",
            },
        ]

    class StubScraper:
        def scrape_webpage(self, url: str) -> str:
            return "Same full body text"

    monkeypatch.setattr(
        "data.providers.rss_news.feedparser.parse",
        lambda url: ParsedFeed(),
    )

    results = fetcher.fetch_market_news("markets", include_body=True, scraper=StubScraper())

    assert len(results) == 1
    assert results[0]["content"] == "Same full body text"
    assert results[0]["article_hash"] == derive_article_hash(
        "Markets rise", "Same full body text"
    )


def test_fetch_market_news_supports_free_form_query_strings(monkeypatch):
    fetcher = RSSNewsFetcher()

    class ParsedFeed:
        entries = [
            {
                "title": "RBI coverage",
                "summary": "Policy update.",
                "link": "https://news.example.com/rbi-story",
                "published": "2026-04-11",
            }
        ]

    def fake_parse(url: str):
        assert (
            url
            == "https://news.google.com/rss/search?"
            "q=when%3A7d+site%3Amoneycontrol.com+RBI+policy+update"
            "&hl=en-IN&gl=IN&ceid=IN:en"
        )
        return ParsedFeed()

    monkeypatch.setattr("data.providers.rss_news.feedparser.parse", fake_parse)

    results = fetcher.fetch_market_news("RBI policy update")

    assert len(results) == 1
    assert results[0]["title"] == "RBI coverage"


def test_fetch_market_news_uses_requested_time_range_for_free_form_queries(monkeypatch):
    fetcher = RSSNewsFetcher()

    class ParsedFeed:
        entries = []

    def fake_parse(url: str):
        assert (
            url
            == "https://news.google.com/rss/search?"
            "q=when%3A30d+site%3Amoneycontrol.com+RBI+policy+update"
            "&hl=en-IN&gl=IN&ceid=IN:en"
        )
        return ParsedFeed()

    monkeypatch.setattr("data.providers.rss_news.feedparser.parse", fake_parse)

    fetcher.fetch_market_news("RBI policy update", time_range="m")
