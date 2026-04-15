from datetime import UTC, datetime

from data.news_pipeline.models import CompanyContext, ExtractionResult, RawSearchResult


def test_raw_search_result_supports_pipeline_metadata():
    item = RawSearchResult(
        ticker="RELIANCE",
        company_name="Reliance Industries",
        market="IN",
        title="Reliance announces results",
        url="https://example.com/story",
        source_domain="example.com",
        source_type="rss",
        query_intent="earnings",
        search_provider="rss",
        publish_time=datetime(2026, 4, 12, tzinfo=UTC),
    )

    assert item.market == "IN"
    assert item.query_intent == "earnings"


def test_company_context_defaults_to_india_market():
    company = CompanyContext(ticker="RELIANCE", company_name="Reliance Industries")

    assert company.market == "IN"
    assert company.ticker == "RELIANCE"


def test_extraction_result_tracks_quality_flags():
    result = ExtractionResult(
        article_text="Reliance Industries announced results " * 20,
        word_count=120,
        extraction_status="full",
        paywall_detected=False,
        relevance_check=True,
    )

    assert result.extraction_status == "full"
    assert result.word_count == 120
