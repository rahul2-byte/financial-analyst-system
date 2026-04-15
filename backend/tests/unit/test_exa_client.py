from __future__ import annotations

from datetime import UTC, datetime

import pytest

from data.news_pipeline.exa_client import ExaSearchClient


class _StubResponse:
    def __init__(self, results):
        self.results = results


class _StubExa:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.calls = []

    def search_and_contents(self, query: str, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return _StubResponse(
            [
                {
                    "title": "HDFC Bank raises rates",
                    "url": "https://example.com/hdfc-rates",
                    "publishedDate": "2026-04-10T12:00:00Z",
                    "author": "Desk",
                    "text": "HDFC Bank changed deposit rates.",
                }
            ]
        )


@pytest.mark.asyncio
async def test_exa_client_builds_search_and_contents_request():
    created = []

    def factory(api_key: str):
        client = _StubExa(api_key)
        created.append(client)
        return client

    client = ExaSearchClient(api_key="test-key", client_factory=factory)
    results = await client.search(
        query="HDFC Bank latest news India",
        num_results=20,
        start_published_date=datetime(2026, 3, 1, tzinfo=UTC),
    )

    assert len(results) == 1
    assert created[0].api_key == "test-key"
    assert created[0].calls[0]["query"] == "HDFC Bank latest news India"
    assert created[0].calls[0]["num_results"] == 20
    assert created[0].calls[0]["category"] == "news"
    assert created[0].calls[0]["text"] == {"max_characters": 4000}
