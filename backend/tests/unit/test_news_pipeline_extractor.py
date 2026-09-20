from __future__ import annotations

from typing import ClassVar

import httpx
from data.news_pipeline.extractor import ArticleExtractor


def test_extractor_marks_snippet_only_when_all_extractors_fail(monkeypatch):
    extractor = ArticleExtractor()

    monkeypatch.setattr(extractor, "_extract_with_trafilatura", lambda url: None)
    monkeypatch.setattr(extractor, "_extract_pdf_text", lambda url, max_pages=15: None)

    result = extractor.extract(
        url="https://example.com/story",
        source_domain="example.com",
        company_name="Reliance Industries",
        ticker="RELIANCE",
        snippet="Short snippet text",
        source_type="rss",
    )

    assert result.extraction_status == "snippet_only"
    assert result.article_text == "Short snippet text"


def test_extractor_flags_partial_when_text_under_100_words(monkeypatch):
    extractor = ArticleExtractor()
    short_text = "Reliance Industries update " * 10

    monkeypatch.setattr(extractor, "_extract_with_trafilatura", lambda url: short_text)

    result = extractor.extract(
        url="https://example.com/story",
        source_domain="example.com",
        company_name="Reliance Industries",
        ticker="RELIANCE",
        snippet="ignored",
        source_type="rss",
    )

    assert result.extraction_status == "partial"
    assert result.relevance_check is True


def test_extractor_detects_paywall_phrase(monkeypatch):
    extractor = ArticleExtractor()
    paywalled = (
        "Please subscribe to read this article about Reliance Industries in full."
    )

    monkeypatch.setattr(extractor, "_extract_with_trafilatura", lambda url: paywalled)

    result = extractor.extract(
        url="https://example.com/story",
        source_domain="example.com",
        company_name="Reliance Industries",
        ticker="RELIANCE",
        snippet="ignored",
        source_type="rss",
    )

    assert result.paywall_detected is True


def test_extractor_marks_irrelevant_when_company_not_present(monkeypatch):
    extractor = ArticleExtractor()
    unrelated = (
        "This article discusses another company and never names the target issuer." * 5
    )

    monkeypatch.setattr(extractor, "_extract_with_trafilatura", lambda url: unrelated)

    result = extractor.extract(
        url="https://example.com/story",
        source_domain="example.com",
        company_name="Reliance Industries",
        ticker="RELIANCE",
        snippet="ignored",
        source_type="rss",
    )

    assert result.relevance_check is False


def test_extractor_matches_common_company_name_alias(monkeypatch):
    extractor = ArticleExtractor()
    article = "India's HDFC Bank reported an update for customers."

    monkeypatch.setattr(extractor, "_extract_with_trafilatura", lambda url: article)

    result = extractor.extract(
        url="https://example.com/story",
        source_domain="example.com",
        company_name="HDFC BANK LTD",
        ticker="HDFCBANK.NS",
        snippet="ignored",
        source_type="news",
    )

    assert result.relevance_check is True


def test_safe_get_stops_after_stream_exceeds_byte_limit(monkeypatch):
    extractor = ArticleExtractor()
    chunks_seen = 0

    class Response:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}
        request = httpx.Request("GET", "https://example.com/story")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def raise_for_status(self):
            return None

        def iter_bytes(self):
            nonlocal chunks_seen
            for chunk in (b"1234", b"56", b"789"):
                chunks_seen += 1
                yield chunk

    monkeypatch.setattr("data.news_pipeline.extractor.MAX_ARTICLE_BYTES", 5)
    monkeypatch.setattr(
        "data.news_pipeline.extractor.socket.getaddrinfo",
        lambda *args: [(None, None, None, None, ("93.184.216.34", 443))],
    )
    monkeypatch.setattr(
        "data.news_pipeline.extractor.httpx.stream", lambda *args, **kwargs: Response()
    )

    assert extractor._safe_get("https://example.com/story") is None
    assert chunks_seen == 2


def test_safe_get_validates_and_follows_bounded_redirects(monkeypatch):
    extractor = ArticleExtractor()
    urls = []

    class Response:
        def __init__(self, url, status_code, headers=None, chunks=()):
            self.status_code = status_code
            self.headers = headers or {}
            self.request = httpx.Request("GET", url)
            self._chunks = chunks

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def raise_for_status(self):
            return None

        def iter_bytes(self):
            yield from self._chunks

    def stream(_method, url, **_kwargs):
        urls.append(url)
        if url == "https://example.com/start":
            return Response(url, 302, {"location": "/final"})
        return Response(url, 200, chunks=(b"article",))

    monkeypatch.setattr(
        "data.news_pipeline.extractor.socket.getaddrinfo",
        lambda *args: [(None, None, None, None, ("93.184.216.34", 443))],
    )
    monkeypatch.setattr("data.news_pipeline.extractor.httpx.stream", stream)

    response = extractor._safe_get("https://example.com/start")

    assert response is not None
    assert response.content == b"article"
    assert urls == ["https://example.com/start", "https://example.com/final"]


def test_safe_get_returns_none_for_failed_source(monkeypatch):
    extractor = ArticleExtractor()
    request = httpx.Request("GET", "https://example.com/story")

    def stream(*args, **kwargs):
        raise httpx.ConnectError("source unavailable", request=request)

    monkeypatch.setattr(
        "data.news_pipeline.extractor.socket.getaddrinfo",
        lambda *args: [(None, None, None, None, ("93.184.216.34", 443))],
    )
    monkeypatch.setattr("data.news_pipeline.extractor.httpx.stream", stream)

    assert extractor._safe_get("https://example.com/story") is None
