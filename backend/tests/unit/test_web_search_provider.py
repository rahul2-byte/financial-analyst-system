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


def test_scrape_webpage_returns_clean_article_text_without_html_markup(monkeypatch):
    provider = WebSearchProvider()

    html = b"""
    <html>
      <body>
        <header>Header nav</header>
        <nav>Navigation</nav>
        <div class="related-stories">Related links</div>
        <article>
          <h1>Story title</h1>
          <p>Lead paragraph.</p>
          <p>Second paragraph with <strong>markup</strong>.</p>
          <p>This is a lot of extra text to ensure that the content length exceeds the 300 character threshold. We want to make sure the test still passes even with the new length check. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Adding more text to be absolutely sure. Adding more text to be absolutely sure. Adding more text to be absolutely sure. Adding more text to be absolutely sure. Adding more text to be absolutely sure. Adding more text to be absolutely sure. Adding more text to be absolutely sure. Adding more text to be absolutely sure. Adding more text to be absolutely sure. Adding more text to be absolutely sure. Adding more text to be absolutely sure. Adding more text to be absolutely sure. Adding more text to be absolutely sure. Adding more text to be absolutely sure. Adding more text to be absolutely sure.</p>
        </article>
        <div class="newsletter-signup">Daily newsletter</div>
        <footer>Footer links</footer>
      </body>
    </html>
    """

    class StubResponse:
        content = html
        text = html.decode()

        def raise_for_status(self):
            return None

    def fake_get(url, headers, timeout):
        assert url == "https://news.example.com/story"
        assert headers == provider.headers
        assert timeout == 10
        return StubResponse()

    monkeypatch.setattr("data.providers.web_search.requests.get", fake_get)

    text = provider.scrape_webpage("https://news.example.com/story")

    assert "Lead paragraph." in text
    assert "Second paragraph with markup." in text
    assert "<strong>" not in text
    assert "Header nav" not in text
    assert "Navigation" not in text
    assert "Related links" not in text
    assert "Daily newsletter" not in text
    assert "Footer links" not in text


def test_search_general_web_returns_empty_list_on_provider_error():
    provider = WebSearchProvider()

    class FailingDDGS:
        def text(self, query, max_results, timelimit):
            raise RuntimeError("boom")

    provider.ddgs = FailingDDGS()

    result = provider.search_general_web("AAPL")

    assert result == []


def test_search_latest_news_returns_empty_list_on_provider_error():
    provider = WebSearchProvider()

    class FailingDDGS:
        def news(self, query, max_results, timelimit):
            raise RuntimeError("boom")

    provider.ddgs = FailingDDGS()

    result = provider.search_latest_news("AAPL")

    assert result == []
