from __future__ import annotations

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
