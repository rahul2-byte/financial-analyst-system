from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

import pytest
from data.news_pipeline.models import CompanyContext, ExtractionResult, RawSearchResult
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


@pytest.mark.asyncio
async def test_runner_keeps_common_name_alias_when_quality_is_sufficient():
    class _CommonNameSnippetExtractor:
        def extract(self, **kwargs):
            from data.news_pipeline.extractor import ArticleExtractor

            text = kwargs["snippet"]
            relevance = ArticleExtractor()._relevance_check(
                text, kwargs["company_name"], kwargs["ticker"]
            )
            return ExtractionResult(
                article_text=text,
                word_count=len(text.split()),
                extraction_status="snippet_only",
                paywall_detected=False,
                relevance_check=relevance,
            )

    company = CompanyContext(ticker="HDFCBANK.NS", company_name="HDFC BANK LTD")
    raw = RawSearchResult(
        ticker="HDFCBANK.NS",
        company_name="HDFC BANK LTD",
        market="IN",
        title="India's HDFC Bank update",
        url="https://example.com/hdfc-update",
        source_domain="example.com",
        source_type="news",
        query_intent="company_news",
        search_provider="tinyfish",
        snippet="India's HDFC Bank reported an update for customers.",
        publish_time=datetime.now(UTC),
    )
    runner = NewsPipelineRunner(
        connectors=[_StubConnector([raw])],
        extractor=_CommonNameSnippetExtractor(),
        min_quality_score=40,
    )
    runner.url_normalizer.resolve_canonical = lambda url: url

    results = await runner.run(company=company, time_window_days=30)

    assert len(results) == 1
    assert results[0].relevance_check is True


@pytest.mark.asyncio
async def test_runner_can_disable_source_quality_filtering_for_ablation():
    class _LowQualityExtractor:
        def extract(self, **kwargs):
            from data.news_pipeline.models import ExtractionResult

            return ExtractionResult(
                article_text=None,
                word_count=0,
                extraction_status="failed",
                paywall_detected=False,
                relevance_check=False,
            )

    company = CompanyContext(ticker="INFY", company_name="Infosys")
    raw = RawSearchResult(
        ticker="INFY",
        company_name="Infosys",
        market="IN",
        title="Infosys update",
        url="https://example.com/infy",
        source_domain="example.com",
        source_type="news",
        query_intent="company_news",
        search_provider="replay",
        snippet="Infosys update",
        publish_time=datetime(2020, 1, 1, tzinfo=UTC),
    )

    filtered = NewsPipelineRunner(
        connectors=[_StubConnector([raw])],
        extractor=_LowQualityExtractor(),
        min_quality_score=40,
        apply_quality_filter=True,
    )
    unfiltered = NewsPipelineRunner(
        connectors=[_StubConnector([raw])],
        extractor=_LowQualityExtractor(),
        min_quality_score=40,
        apply_quality_filter=False,
    )

    assert await filtered.run(company=company, time_window_days=30) == []
    assert len(await unfiltered.run(company=company, time_window_days=30)) == 1


def test_runner_uses_tinyfish_connector_as_primary_default_source():
    runner = NewsPipelineRunner()

    assert runner.connectors[0].__class__.__name__ == "TinyFishSearchConnector"


@pytest.mark.asyncio
async def test_runner_moves_synchronous_extraction_off_event_loop():
    company = CompanyContext(ticker="INFY", company_name="Infosys")
    raw = RawSearchResult(
        ticker="INFY",
        company_name="Infosys",
        market="IN",
        title="Infosys update",
        url="https://example.com/infy",
        source_domain="example.com",
        source_type="news",
        query_intent="company_news",
        search_provider="fixture",
    )

    class _SlowExtractor:
        def extract(self, **kwargs):
            del kwargs
            time.sleep(0.08)
            return ExtractionResult(
                article_text="Infosys article " * 30,
                word_count=120,
                extraction_status="full",
                paywall_detected=False,
                relevance_check=True,
            )

    runner = NewsPipelineRunner(
        connectors=[_StubConnector([raw])], extractor=_SlowExtractor()
    )
    runner.url_normalizer.resolve_canonical = lambda url: url
    started = time.perf_counter()
    task = asyncio.create_task(runner.run(company=company, time_window_days=30))
    await asyncio.sleep(0.01)
    event_loop_delay = time.perf_counter() - started
    await task

    assert event_loop_delay < 0.05
