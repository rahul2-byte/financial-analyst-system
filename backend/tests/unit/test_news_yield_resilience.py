import pytest
from unittest.mock import patch
from agents.financial.data.data_fetch_node import _fetch_planned_news
from data.processors.text import is_article_relevant


class _StubRunner:
    def __init__(self, records):
        self.records = records

    async def run(self, *, company, time_window_days):
        return list(self.records)


@pytest.mark.asyncio
async def test_snippet_fallback_for_top_results():
    from datetime import UTC, datetime
    from data.news_pipeline.models import NewsPipelineRecord

    records = [
        NewsPipelineRecord(
            ticker="AAPL",
            company_name="Apple",
            market="IN",
            url="http://test.com/1",
            canonical_url="http://test.com/1",
            title="Result 1",
            author=None,
            snippet="Snippet 1",
            article_text="Snippet 1",
            word_count=2,
            publish_time=datetime(2026, 4, 11, tzinfo=UTC),
            retrieval_time=datetime(2026, 4, 11, tzinfo=UTC),
            source_domain="test.com",
            source_type="rss",
            source_tier=2,
            paywall_detected=False,
            extraction_status="snippet_only",
            quality_score=45,
            relevance_check=True,
            is_duplicate=False,
            cluster_id="c1",
            query_intent="breaking_news",
            search_provider="rss",
            pipeline_version="1.0.0",
        ),
        NewsPipelineRecord(
            ticker="AAPL",
            company_name="Apple",
            market="IN",
            url="http://test.com/2",
            canonical_url="http://test.com/2",
            title="Result 2",
            author=None,
            snippet="Snippet 2",
            article_text="Snippet 2",
            word_count=2,
            publish_time=datetime(2026, 4, 11, tzinfo=UTC),
            retrieval_time=datetime(2026, 4, 11, tzinfo=UTC),
            source_domain="test.com",
            source_type="rss",
            source_tier=2,
            paywall_detected=False,
            extraction_status="snippet_only",
            quality_score=45,
            relevance_check=True,
            is_duplicate=False,
            cluster_id="c2",
            query_intent="breaking_news",
            search_provider="rss",
            pipeline_version="1.0.0",
        ),
    ]

    with patch(
        "agents.financial.data.data_fetch_node._build_news_pipeline_runner",
        return_value=_StubRunner(records),
    ):
        results = await _fetch_planned_news(
            objective="Analyze Apple",
            ticker="AAPL",
            company_name="Apple",
            timeframe="1m",
            conversation_history=None,
        )

        r1 = next((r for r in results if r["title"] == "Result 1"), None)
        assert r1 is not None, "Result 1 should be present"
        assert r1["content"] == "Snippet 1"
        assert r1["extraction_status"] == "snippet_only"

        r2 = next((r for r in results if r["title"] == "Result 2"), None)
        assert r2 is not None, "Result 2 should be present"
        assert r2["content"] == "Snippet 2"
        assert r2["extraction_status"] == "snippet_only"


class TestIsArticleRelevant:
    def test_basic_title_match(self):
        article = {"title": "HDFC Bank reports earnings", "content": "Some content"}
        assert (
            is_article_relevant(article, ticker="HDFCBANK", company_name="HDFC Bank")
            is True
        )

    def test_basic_lead_match(self):
        article = {
            "title": "Market update",
            "content": "HDFC Bank showed growth..." + "x" * 500,
        }
        assert (
            is_article_relevant(article, ticker="HDFC", company_name="HDFC Bank")
            is True
        )

    def test_adr_alias_hdb(self):
        article = {
            "title": "HDB shares rise",
            "content": "HDFC Bank US-listed ADR HDB climbed today.",
        }
        assert is_article_relevant(article, ticker="HDFC", adr_aliases=["HDB"]) is True

    def test_lenient_title_match_only(self):
        article = {
            "title": "HDFC Bank CEO speaks",
            "content": "Random unrelated content.",
        }
        assert is_article_relevant(article, ticker="HDFC", lenient=True) is True

    def test_lenient_lead_match_only(self):
        article = {
            "title": "Market overview",
            "content": "HDFC Bank reported..." + "x" * 450,
        }
        assert is_article_relevant(article, ticker="HDFC", lenient=True) is True

    def test_lenient_no_match(self):
        article = {"title": "Unrelated news", "content": "Some other content here."}
        assert is_article_relevant(article, ticker="HDFC", lenient=True) is False

    def test_empty_article(self):
        article = {"title": "", "content": ""}
        assert is_article_relevant(article, ticker="HDFC") is False

    def test_strict_frequency_threshold(self):
        article = {
            "title": "Market report",
            "content": "HDFC HDFC HDFC " + "x" * 500,
        }
        assert is_article_relevant(article, ticker="HDFC", lenient=False) is True

    def test_strict_below_threshold(self):
        article = {
            "title": "Market report",
            "content": "x" * 550 + " HDFC other",  # HDFC appears at position 550+
        }
        assert (
            is_article_relevant(
                article, ticker="HDFC", company_name=None, lenient=False
            )
            is False
        )
