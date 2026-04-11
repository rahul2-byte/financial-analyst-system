import pytest
from data.processors.text import is_article_relevant


def test_relevance_guard_matches_ticker_in_title():
    article = {
        "title": "AAPL reaches new highs",
        "content": "A general article about tech stocks."
    }
    assert is_article_relevant(article, ticker="AAPL") is True


def test_relevance_guard_matches_company_name_in_title():
    article = {
        "title": "Apple launches new iPhone",
        "content": "The company announced various updates today."
    }
    assert is_article_relevant(article, ticker="AAPL", company_name="Apple") is True


def test_relevance_guard_matches_ticker_in_lead_content():
    article = {
        "title": "Daily Market Wrap",
        "content": "AAPL is leading the gains today in the NASDAQ. The rest of the market is flat."
    }
    assert is_article_relevant(article, ticker="AAPL") is True


def test_relevance_guard_matches_ticker_frequency():
    # Ticker doesn't appear in title or lead (first 500 chars)
    # But appears 3+ times in full content
    content = ("Some intro text. " * 50) + " AAPL " + (" more text. " * 10) + " AAPL " + (" more text. " * 10) + " AAPL "
    article = {
        "title": "Market Trends 2024",
        "content": content
    }
    # First 500 chars definitely don't have AAPL
    assert "AAPL" not in content[:500]
    assert is_article_relevant(article, ticker="AAPL") is True


def test_relevance_guard_rejects_unrelated_content():
    article = {
        "title": "Tesla's record quarter",
        "content": "TSLA had a great quarter. No mention of the iPhone maker here."
    }
    assert is_article_relevant(article, ticker="AAPL", company_name="Apple") is False


def test_relevance_guard_handles_case_sensitivity_and_whole_words():
    # Whole word matching: 'AAPLE' should not match 'AAPL'
    article = {
        "title": "AAPLE is not a ticker",
        "content": "Just some random text."
    }
    assert is_article_relevant(article, ticker="AAPL") is False
    
    # Case insensitivity
    article_lower = {
        "title": "aapl update",
        "content": "market news."
    }
    assert is_article_relevant(article_lower, ticker="AAPL") is True


def test_relevance_guard_handles_empty_fields():
    assert is_article_relevant({}, ticker="AAPL") is False
    assert is_article_relevant({"title": ""}, ticker="AAPL") is False
    assert is_article_relevant({"title": "AAPL"}, ticker="") is False
