import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from agents.financial.data.data_fetch_node import _fetch_planned_news
from data.processors.text import is_article_relevant

@pytest.mark.asyncio
async def test_snippet_fallback_for_top_results():
    # Mock search results
    # Rank 1 & 2 will fail scraping and should fall back to snippet
    # Rank 3 will fail scraping and should be filtered out (or keep error, depending on logic)
    mock_search_results = [
        {"title": "Result 1", "body": "Snippet 1", "url": "http://test.com/1", "date": "2024-01-01"},
        {"title": "Result 2", "body": "Snippet 2", "url": "http://test.com/2", "date": "2024-01-01"},
        {"title": "Result 3", "body": "Snippet 3", "url": "http://test.com/3", "date": "2024-01-01"},
    ]
    
    # Mock resources.web_search
    mock_web_search = MagicMock()
    mock_web_search.search.return_value = mock_search_results
    
    # Mock build_news_query_plan
    mock_query_plan = {
        "queries": [
            {"query": "AAPL news", "intent_type": "company_news", "time_range": "m"}
        ]
    }

    with patch("agents.financial.data.data_fetch_node.resources") as mock_res, \
         patch("agents.financial.data.data_fetch_node.build_news_query_plan", return_value=mock_query_plan), \
         patch("agents.financial.data.data_fetch_node.enrich_article_with_body") as mock_enrich, \
         patch("agents.financial.data.data_fetch_node.is_article_relevant", return_value=True):
        
        mock_res.web_search = mock_web_search
        
        # Mock enrichment to always return a paywall block
        def side_effect_enrich(article, scraper):
            return {**article, "content": f"PAYWALL_BLOCKED: {article['url']}"}
        
        mock_enrich.side_effect = side_effect_enrich

        # Execute
        results = await _fetch_planned_news(
            objective="Analyze Apple",
            ticker="AAPL",
            company_name="Apple",
            timeframe="1m",
            conversation_history=None
        )

        # Assertions
        # Result 1 (rank 1) should have fallback content
        r1 = next((r for r in results if r["title"] == "Result 1"), None)
        assert r1 is not None, "Result 1 should be present"
        assert r1["content"] == "Snippet 1"
        assert r1.get("is_snippet_fallback") is True

        # Result 2 (rank 2) should have fallback content
        r2 = next((r for r in results if r["title"] == "Result 2"), None)
        assert r2 is not None, "Result 2 should be present"
        assert r2["content"] == "Snippet 2"
        assert r2.get("is_snippet_fallback") is True

        # Result 3 (rank 3) should NOT be present if it's filtered out when scraping fails
        # Or it might contain the error message if the logic keeps it but fails relevance.
        # But in Task 2 requirement: "For articles with search_rank > 2: Continue requiring full-text. 
        # If scraping fails, these articles should still be filtered out"
        r3 = next((r for r in results if r["title"] == "Result 3"), None)
        assert r3 is None or "PAYWALL_BLOCKED" not in r3["content"]
        if r3:
            # If it's there, it MUST NOT be the snippet fallback
            assert r3.get("is_snippet_fallback") is not True
            # And it shouldn't be the error message based on the requirement to filter out
            assert not r3["content"].startswith("PAYWALL_BLOCKED")


class TestIsArticleRelevant:
    def test_basic_title_match(self):
        article = {"title": "HDFC Bank reports earnings", "content": "Some content"}
        assert is_article_relevant(article, ticker="HDFCBANK", company_name="HDFC Bank") is True

    def test_basic_lead_match(self):
        article = {"title": "Market update", "content": "HDFC Bank showed growth..." + "x" * 500}
        assert is_article_relevant(article, ticker="HDFC", company_name="HDFC Bank") is True

    def test_adr_alias_hdb(self):
        article = {"title": "HDB shares rise", "content": "HDFC Bank US-listed ADR HDB climbed today."}
        assert is_article_relevant(article, ticker="HDFC", adr_aliases=["HDB"]) is True

    def test_lenient_title_match_only(self):
        article = {"title": "HDFC Bank CEO speaks", "content": "Random unrelated content."}
        assert is_article_relevant(article, ticker="HDFC", lenient=True) is True

    def test_lenient_lead_match_only(self):
        article = {"title": "Market overview", "content": "HDFC Bank reported..." + "x" * 450}
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
        assert is_article_relevant(article, ticker="HDFC", company_name=None, lenient=False) is False
