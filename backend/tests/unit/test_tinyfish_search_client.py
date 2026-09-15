from datetime import UTC, datetime

import pytest
from data.news_pipeline.tinyfish_client import TinyFishSearchClient


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "query": "HDFC Bank latest news India",
            "results": [
                {
                    "position": 1,
                    "title": "HDFC Bank raises rates",
                    "url": "https://example.com/hdfc-rates",
                    "snippet": "HDFC Bank changed deposit rates.",
                    "published_date": "2026-04-10T12:00:00Z",
                }
            ],
        }


class _Client:
    def __init__(self):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, *, headers, params):
        self.calls.append({"url": url, "headers": headers, "params": params})
        return _Response()


@pytest.mark.asyncio
async def test_tinyfish_search_client_requests_news_results_with_date_filter():
    http_client = _Client()
    client = TinyFishSearchClient(
        api_key="test-key", client_factory=lambda timeout: http_client
    )

    results = await client.search(
        query="HDFC Bank latest news India",
        num_results=20,
        start_published_date=datetime(2026, 3, 1, tzinfo=UTC),
    )

    assert results[0]["title"] == "HDFC Bank raises rates"
    assert http_client.calls[0] == {
        "url": "https://api.search.tinyfish.ai",
        "headers": {"X-API-Key": "test-key"},
        "params": {
            "query": "HDFC Bank latest news India",
            "limit": 20,
            "domain_type": "news",
            "after_date": "2026-03-01",
        },
    }
