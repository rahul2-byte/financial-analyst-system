import pytest
from unittest.mock import MagicMock, patch
from data.providers.web_search import WebSearchProvider


@pytest.fixture
def provider():
    return WebSearchProvider()


def test_scrape_webpage_detects_paywall_marker(provider):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body><h1>Exclusive Article</h1><p>Subscription required to read more.</p></body></html>"
    mock_response.content = mock_response.text.encode("utf-8")

    with patch("requests.get", return_value=mock_response):
        result = provider.scrape_webpage("https://example.com/paywalled")
        assert result == "PAYWALL_BLOCKED: https://example.com/paywalled"


def test_scrape_webpage_detects_short_content(provider):
    # Content < 300 chars
    short_text = "A very short article that should be rejected as low quality or a cookie wall."
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = f"<html><body><article><p>{short_text}</p></article></body></html>"
    mock_response.content = mock_response.text.encode("utf-8")

    with patch("requests.get", return_value=mock_response):
        result = provider.scrape_webpage("https://example.com/short")
        assert result == "PAYWALL_BLOCKED: https://example.com/short"


def test_scrape_webpage_cleans_noise_and_returns_text(provider):
    # Sufficiently long content with noise
    long_text = "This is a meaningful article about financial markets. " * 10
    html = f"""
    <html>
        <head><title>Market News</title></head>
        <body>
            <nav>Menu items here</nav>
            <article>
                <h1>Market Update</h1>
                <p>{long_text}</p>
                <div class="advertisement">Buy this now!</div>
            </article>
            <footer>Footer info</footer>
            <script>console.log('noise');</script>
        </body>
    </html>
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_response.content = html.encode("utf-8")

    with patch("requests.get", return_value=mock_response):
        result = provider.scrape_webpage("https://example.com/good")
        assert "Market Update" in result
        assert long_text.strip() in result
        assert "Menu items here" not in result
        assert "Buy this now!" not in result
        assert "Footer info" not in result
        assert len(result) >= 300


def test_scrape_webpage_handles_request_errors(provider):
    with patch("requests.get", side_effect=Exception("Network error")):
        result = provider.scrape_webpage("https://example.com/error")
        assert "Failed to scrape" in result
        assert "Network error" in result
