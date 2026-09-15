from __future__ import annotations

from datetime import UTC, datetime

import pytest
from data.news_pipeline.models import CompanyContext, RawSearchResult
from data.news_pipeline.runner import NewsPipelineRunner


class _StubConnector:
    def __init__(self, results):
        self.results = results

    async def fetch(self, company, *, time_window_days):
        return list(self.results)


class _StubExtractor:
    def extract(self, **kwargs):
        from data.news_pipeline.models import ExtractionResult

        return ExtractionResult(
            article_text=f"{kwargs['company_name']} article body " * 30,
            word_count=120,
            extraction_status="full",
            paywall_detected=False,
            relevance_check=True,
        )


@pytest.mark.asyncio
async def test_runner_returns_ranked_records_from_multiple_connectors():
    company = CompanyContext(
        ticker="RELIANCE",
        company_name="Reliance Industries",
        nse_symbol="RELIANCE",
        bse_code="500325",
        sector="Energy",
    )
    publish_time = datetime(2026, 4, 12, tzinfo=UTC)
    raw = RawSearchResult(
        ticker="RELIANCE",
        company_name="Reliance Industries",
        market="IN",
        title="Reliance Industries announces results",
        url="https://www.bseindia.com/example",
        source_domain="bseindia.com",
        source_type="filing",
        query_intent="earnings",
        search_provider="bse",
        publish_time=publish_time,
    )

    runner = NewsPipelineRunner(
        connectors=[_StubConnector([raw]), _StubConnector([])],
        extractor=_StubExtractor(),
        max_articles_per_company=50,
        min_quality_score=40,
        pipeline_version="1.0.0",
    )

    results = await runner.run(company=company, time_window_days=30)

    assert len(results) == 1
    assert results[0].source_tier == 1
    assert results[0].quality_score >= 40
    assert results[0].canonical_url == "https://www.bseindia.com/example"


@pytest.mark.asyncio
async def test_runner_filters_blocked_domains():
    company = CompanyContext(ticker="INFY", company_name="Infosys")
    publish_time = datetime(2026, 4, 12, tzinfo=UTC)
    blocked = RawSearchResult(
        ticker="INFY",
        company_name="Infosys",
        market="IN",
        title="Infosys article",
        url="https://zacks.com/infosys",
        source_domain="zacks.com",
        source_type="search",
        query_intent="breaking_news",
        search_provider="yahoo_finance",
        publish_time=publish_time,
    )

    runner = NewsPipelineRunner(
        connectors=[_StubConnector([blocked])],
        extractor=_StubExtractor(),
        max_articles_per_company=50,
        min_quality_score=40,
        pipeline_version="1.0.0",
    )

    results = await runner.run(company=company, time_window_days=30)

    assert results == []


@pytest.mark.asyncio
async def test_runner_keeps_tinyfish_records_for_alias_based_queries():
    company = CompanyContext(ticker="HDFCBANK", company_name="HDFC BANK LTD")
    publish_time = datetime(2026, 4, 12, tzinfo=UTC)
    raw = RawSearchResult(
        ticker="HDFCBANK",
        company_name="HDFC BANK LTD",
        market="IN",
        title="HDFC Bank announces branch expansion",
        url="https://example.com/hdfc-expansion",
        source_domain="example.com",
        source_type="search",
        query_intent="strategic",
        search_provider="tinyfish",
        snippet="HDFC Bank will expand its branch network.",
        publish_time=publish_time,
    )

    runner = NewsPipelineRunner(
        connectors=[_StubConnector([raw])],
        extractor=_StubExtractor(),
        max_articles_per_company=50,
        min_quality_score=40,
        pipeline_version="1.0.0",
    )

    results = await runner.run(company=company, time_window_days=30)

    assert len(results) == 1
    assert results[0].query_intent == "strategic"
    assert results[0].search_provider == "tinyfish"


def test_runner_uses_tinyfish_connector_as_primary_default_source():
    runner = NewsPipelineRunner()

    assert runner.connectors[0].__class__.__name__ == "TinyFishSearchConnector"
