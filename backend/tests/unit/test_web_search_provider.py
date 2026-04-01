from unittest.mock import MagicMock

from data.providers.web_search import WebSearchProvider


def test_web_search_provider_exposes_search_facade():
    provider = WebSearchProvider()
    assert hasattr(provider, "search")


def test_search_facade_dispatches_to_general_search_by_default():
    provider = WebSearchProvider()
    provider.search_general_web = MagicMock(return_value=[{"title": "g"}])
    provider.search_latest_news = MagicMock(return_value=[{"title": "n"}])

    result = provider.search("AAPL")

    provider.search_general_web.assert_called_once_with(
        "AAPL", max_results=5, time_range="m"
    )
    provider.search_latest_news.assert_not_called()
    assert result == [{"title": "g"}]


def test_search_facade_dispatches_to_news_search_when_mode_news():
    provider = WebSearchProvider()
    provider.search_general_web = MagicMock(return_value=[{"title": "g"}])
    provider.search_latest_news = MagicMock(return_value=[{"title": "n"}])

    result = provider.search("AAPL", mode="news", time_range="w", max_results=3)

    provider.search_latest_news.assert_called_once_with(
        "AAPL", max_results=3, time_range="w"
    )
    provider.search_general_web.assert_not_called()
    assert result == [{"title": "n"}]
