from datetime import UTC, datetime

import pytest
from app.observability.provider_archive import ProviderArchive, ProviderSnapshot
from data.news_pipeline.models import CompanyContext
from data.news_pipeline.replay import ReplayArticleExtractor, ReplayNewsConnector
from data.news_pipeline.runner import NewsPipelineRunner


@pytest.mark.asyncio
async def test_replay_news_pipeline_uses_archived_content_without_url_fetch(tmp_path):
    archive = ProviderArchive(tmp_path)
    snapshot = archive.store(
        ProviderSnapshot(
            provider="news_pipeline",
            operation="fetch_news",
            payload=[
                {
                    "ticker": "ABC.NS",
                    "title": "ABC update",
                    "url": "https://news.example/abc",
                    "summary": "ABC update",
                    "content": "ABC.NS reported an update. " * 20,
                    "published_date": "2026-09-18T00:00:00+00:00",
                }
            ],
            fetched_at=datetime(2026, 9, 18, tzinfo=UTC),
        )
    )
    connector = ReplayNewsConnector(archive, snapshot.content_hash)
    runner = NewsPipelineRunner(
        connectors=[connector],
        extractor=ReplayArticleExtractor(connector.article_text_by_url),
        apply_quality_filter=False,
    )

    results = await runner.run(
        company=CompanyContext(ticker="ABC.NS", company_name="ABC"),
        time_window_days=30,
    )

    assert len(results) == 1
    assert results[0].extraction_status == "full"
    assert results[0].url == "https://news.example/abc"


@pytest.mark.asyncio
async def test_replay_news_pipeline_rejects_missing_snapshot(tmp_path):
    connector = ReplayNewsConnector(ProviderArchive(tmp_path), None)

    with pytest.raises(RuntimeError, match="fetch_news"):
        await connector.fetch(
            CompanyContext(ticker="ABC.NS", company_name="ABC"),
            time_window_days=30,
        )


def test_replay_extractor_matches_common_company_name_alias():
    extractor = ReplayArticleExtractor(
        {"https://news.example/hdfc": "India's HDFC Bank reported an update."}
    )

    result = extractor.extract(
        url="https://news.example/hdfc",
        source_domain="news.example",
        company_name="HDFC BANK LTD",
        ticker="HDFCBANK.NS",
        snippet="ignored",
        source_type="news",
    )

    assert result.relevance_check is True
