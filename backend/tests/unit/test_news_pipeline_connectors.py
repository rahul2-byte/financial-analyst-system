from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import pytest

from data.news_pipeline.connectors import (
    ExaSearchConnector,
    _matches_company_terms,
)
from data.news_pipeline.models import CompanyContext


@dataclass(slots=True)
class _ExaResult:
    url: str
    id: str
    title: str
    published_date: str | None = None
    author: str | None = None
    text: str | None = None
    summary: str | None = None


def test_matches_company_terms_requires_alias_boundaries():
    company = CompanyContext(ticker="ACE", company_name="ACE LTD")

    assert not _matches_company_terms(
        "Investors said the race for market share is intensifying.", company
    )


@pytest.mark.asyncio
async def test_exa_search_connector_builds_detailed_queries_and_maps_results():
    company = CompanyContext(
        ticker="HDFCBANK",
        company_name="HDFC BANK LTD",
        nse_symbol="HDFCBANK",
    )

    published = datetime.now(timezone.utc) - timedelta(days=1)

    class _Client:
        def __init__(self):
            self.calls = []

        async def search(self, *, query, num_results, start_published_date):
            self.calls.append(
                {
                    "query": query,
                    "num_results": num_results,
                    "start_published_date": start_published_date,
                }
            )
            return [
                _ExaResult(
                    title="HDFC Bank raises deposit rates",
                    text="HDFC Bank updated rates for retail deposits.",
                    url="https://example.com/hdfc-rates",
                    id="https://example.com/hdfc-rates",
                    published_date=published.isoformat(),
                )
            ]

    client = _Client()
    connector = ExaSearchConnector(client=client, max_results_per_query=20)

    results = await connector.fetch(company, time_window_days=30)

    assert results
    assert results[0].title == "HDFC Bank raises deposit rates"
    assert results[0].search_provider == "exa"
    assert client.calls[0]["num_results"] == 20
    assert any("HDFC BANK" in call["query"] for call in client.calls)


@pytest.mark.asyncio
async def test_exa_search_connector_maps_exa_result_object_fields():
    company = CompanyContext(
        ticker="HDFCBANK",
        company_name="HDFC BANK LTD",
        nse_symbol="HDFCBANK",
    )

    published = datetime.now(timezone.utc) - timedelta(days=1)

    class _Client:
        async def search(self, *, query, num_results, start_published_date):
            return [
                _ExaResult(
                    title="HDFC Bank raises deposit rates",
                    text="HDFC Bank updated retail deposit rates across products.",
                    url="https://example.com/hdfc-rates",
                    id="https://example.com/hdfc-rates",
                    published_date=published.isoformat(),
                    author="PTI",
                )
            ]

    connector = ExaSearchConnector(client=_Client(), max_results_per_query=20)

    results = await connector.fetch(company, time_window_days=30)

    assert len(results) == 1
    assert results[0].title == "HDFC Bank raises deposit rates"
    assert (
        results[0].snippet
        == "HDFC Bank updated retail deposit rates across products."
    )
    assert results[0].author == "PTI"
    assert results[0].publish_time == published


@pytest.mark.asyncio
async def test_exa_search_connector_skips_stale_results_outside_time_window():
    company = CompanyContext(
        ticker="HDFCBANK",
        company_name="HDFC BANK LTD",
        nse_symbol="HDFCBANK",
    )
    stale_published = datetime.now(timezone.utc) - timedelta(days=10)

    class _Client:
        async def search(self, *, query, num_results, start_published_date):
            return [
                _ExaResult(
                    title="HDFC Bank raises deposit rates",
                    text="HDFC Bank updated retail deposit rates across products.",
                    url="https://example.com/hdfc-rates",
                    id="https://example.com/hdfc-rates",
                    published_date=stale_published.isoformat(),
                )
            ]

    connector = ExaSearchConnector(client=_Client(), max_results_per_query=20)

    results = await connector.fetch(company, time_window_days=7)

    assert results == []


@pytest.mark.asyncio
async def test_exa_search_connector_explodes_portal_payload_into_headlines():
    company = CompanyContext(
        ticker="HDB",
        company_name="HDFC Bank Limited",
        nse_symbol="HDFCBANK",
    )

    published = datetime.now(timezone.utc) - timedelta(days=1)

    portal_text = """HDFC Bank Limited (HDB) Latest Stock News & Headlines - Yahoo Finance

Published Date: __PUBLISHED__
Author: None

    ### HDFC Bank expands branch network in semi-urban markets

    Reuters 2d ago

    ### HDFC Bank raises deposit rates for select retail products

    Reuters 3d ago

    ### India's HDFC Bank delayed action in AT-1 bond mis-selling, former chair tells CNBC-TV18

Reuters 12d ago
""".replace("__PUBLISHED__", published.isoformat())

    class _Client:
        async def search(self, *, query, num_results, start_published_date):
            return [
                _ExaResult(
                    title="HDFC Bank Limited (HDB) Latest Stock News & Headlines",
                    url="https://finance.yahoo.com/quote/HDB/news/",
                    id="https://finance.yahoo.com/quote/HDB/news/",
                    text=portal_text,
                    published_date=published.isoformat(),
                )
            ]

    connector = ExaSearchConnector(client=_Client(), max_results_per_query=20)

    results = await connector.fetch(company, time_window_days=30)

    assert len(results) == 3
    assert [item.title for item in results] == [
        "HDFC Bank expands branch network in semi-urban markets",
        "HDFC Bank raises deposit rates for select retail products",
        "India's HDFC Bank delayed action in AT-1 bond mis-selling, former chair tells CNBC-TV18",
    ]
    assert all(item.url == "https://finance.yahoo.com/quote/HDB/news/" for item in results)
    assert all(item.search_provider == "exa" for item in results)


@pytest.mark.asyncio
async def test_exa_search_connector_filters_stale_portal_headlines_using_child_recency():
    company = CompanyContext(
        ticker="HDB",
        company_name="HDFC Bank Limited",
        nse_symbol="HDFCBANK",
    )

    published = datetime.now(timezone.utc) - timedelta(hours=2)

    portal_text = """HDFC Bank Limited (HDB) Latest Stock News & Headlines - Yahoo Finance

Published Date: __PUBLISHED__

### HDFC Bank expands branch network in semi-urban markets

Reuters 2d ago

### India's HDFC Bank delayed action in AT-1 bond mis-selling, former chair tells CNBC-TV18

Reuters 12d ago
""".replace("__PUBLISHED__", published.isoformat())

    class _Client:
        async def search(self, *, query, num_results, start_published_date):
            return [
                _ExaResult(
                    title="HDFC Bank Limited (HDB) Latest Stock News & Headlines",
                    url="https://finance.yahoo.com/quote/HDB/news/",
                    id="https://finance.yahoo.com/quote/HDB/news/",
                    text=portal_text,
                    published_date=published.isoformat(),
                )
            ]

    connector = ExaSearchConnector(client=_Client(), max_results_per_query=20)

    results = await connector.fetch(company, time_window_days=7)

    assert len(results) == 1
    assert results[0].title == "HDFC Bank expands branch network in semi-urban markets"


@pytest.mark.asyncio
async def test_exa_search_connector_keeps_fresh_portal_child_when_wrapper_is_stale():
    company = CompanyContext(
        ticker="HDB",
        company_name="HDFC Bank Limited",
        nse_symbol="HDFCBANK",
    )

    stale_published = datetime.now(timezone.utc) - timedelta(days=5)

    portal_text = """HDFC Bank Limited (HDB) Latest Stock News & Headlines - Yahoo Finance

Published Date: __PUBLISHED__

### HDFC Bank raises deposit rates for select retail products

Reuters 2h ago

### India's HDFC Bank delayed action in AT-1 bond mis-selling, former chair tells CNBC-TV18

Reuters 12d ago
""".replace("__PUBLISHED__", stale_published.isoformat())

    class _Client:
        async def search(self, *, query, num_results, start_published_date):
            return [
                _ExaResult(
                    title="HDFC Bank Limited (HDB) Latest Stock News & Headlines",
                    url="https://finance.yahoo.com/quote/HDB/news/",
                    id="https://finance.yahoo.com/quote/HDB/news/",
                    text=portal_text,
                    published_date=stale_published.isoformat(),
                )
            ]

    connector = ExaSearchConnector(client=_Client(), max_results_per_query=20)

    results = await connector.fetch(company, time_window_days=1)

    assert len(results) == 1
    assert results[0].title == "HDFC Bank raises deposit rates for select retail products"


@pytest.mark.asyncio
async def test_exa_search_connector_filters_irrelevant_portal_headlines():
    company = CompanyContext(
        ticker="HDB",
        company_name="HDFC Bank Limited",
        nse_symbol="HDFCBANK",
    )

    portal_text = """HDFC Bank Limited (HDB) Latest Stock News & Headlines - Yahoo Finance

### Branch expansion gathers pace in semi-urban markets

Reuters 3d ago

HDFC Bank said the new rollout will focus on deposit growth in underpenetrated districts.

### RBI proposes bank boards focus more on policy than daily operations

Reuters 12d ago

The consultation paper covers governance expectations for lenders.
"""

    class _Client:
        async def search(self, *, query, num_results, start_published_date):
            return [
                _ExaResult(
                    title="HDFC Bank Limited (HDB) Latest Stock News & Headlines",
                    url="https://finance.yahoo.com/quote/HDB/news/",
                    id="https://finance.yahoo.com/quote/HDB/news/",
                    text=portal_text,
                )
            ]

    connector = ExaSearchConnector(client=_Client(), max_results_per_query=20)

    results = await connector.fetch(company, time_window_days=30)

    assert len(results) == 1
    assert results[0].title == "Branch expansion gathers pace in semi-urban markets"


@pytest.mark.asyncio
async def test_exa_search_connector_drops_malformed_portal_pages_without_headlines():
    company = CompanyContext(
        ticker="HDB",
        company_name="HDFC Bank Limited",
        nse_symbol="HDFCBANK",
    )

    portal_text = """HDFC Bank Limited (HDB) Latest Stock News & Headlines - Yahoo Finance

###

Reuters 2d ago

###

Reuters 1d ago
"""

    class _Client:
        async def search(self, *, query, num_results, start_published_date):
            return [
                _ExaResult(
                    title="HDFC Bank Limited (HDB) Latest Stock News & Headlines",
                    url="https://finance.yahoo.com/quote/HDB/news/",
                    id="https://finance.yahoo.com/quote/HDB/news/",
                    text=portal_text,
                    published_date=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                )
            ]

    connector = ExaSearchConnector(client=_Client(), max_results_per_query=20)

    results = await connector.fetch(company, time_window_days=30)

    assert results == []


@pytest.mark.asyncio
async def test_exa_search_connector_deduplicates_exploded_headlines():
    company = CompanyContext(ticker="HDB", company_name="HDFC Bank Limited")

    portal_text = """HDFC Bank Limited (HDB) Latest Stock News & Headlines - Yahoo Finance

### HDFC Bank delayed action in AT-1 bond mis-selling, former chair tells CNBC-TV18

Reuters 12d ago

### HDFC Bank delayed action in AT-1 bond mis-selling, former chair tells CNBC-TV18

Reuters 12d ago
"""

    class _Client:
        async def search(self, *, query, num_results, start_published_date):
            return [
                _ExaResult(
                    title="HDFC Bank Limited (HDB) Latest Stock News & Headlines",
                    url="https://finance.yahoo.com/quote/HDB/news/",
                    id="https://finance.yahoo.com/quote/HDB/news/",
                    text=portal_text,
                    published_date=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                )
            ]

    connector = ExaSearchConnector(client=_Client(), max_results_per_query=20)

    results = await connector.fetch(company, time_window_days=30)

    assert len(results) == 1
    assert (
        results[0].title
        == "HDFC Bank delayed action in AT-1 bond mis-selling, former chair tells CNBC-TV18"
    )


@pytest.mark.asyncio
async def test_exa_search_connector_does_not_explode_article_page_with_subheadings():
    company = CompanyContext(
        ticker="HDB",
        company_name="HDFC Bank Limited",
        nse_symbol="HDFCBANK",
    )

    published = datetime.now(timezone.utc) - timedelta(days=1)

    article_text = """HDFC Bank expands branch network in semi-urban markets.

### Why this matters

HDFC Bank said the expansion supports deposit growth in newer markets.

### What comes next

Executives expect additional branch openings over the next two quarters.
"""

    class _Client:
        async def search(self, *, query, num_results, start_published_date):
            return [
                _ExaResult(
                    title="HDFC Bank expands branch network in semi-urban markets",
                    url="https://example.com/news/hdfc-bank-branch-expansion",
                    id="https://example.com/news/hdfc-bank-branch-expansion",
                    text=article_text,
                    published_date=published.isoformat(),
                )
            ]

    connector = ExaSearchConnector(client=_Client(), max_results_per_query=20)

    results = await connector.fetch(company, time_window_days=30)

    assert len(results) == 1
    assert results[0].title == "HDFC Bank expands branch network in semi-urban markets"
    assert results[0].url == "https://example.com/news/hdfc-bank-branch-expansion"
    assert results[0].snippet == article_text.strip()


@pytest.mark.asyncio
async def test_exa_search_connector_uses_summary_when_text_missing():
    company = CompanyContext(ticker="HDB", company_name="HDFC Bank Limited")

    published = datetime.now(timezone.utc) - timedelta(days=1)

    class _Client:
        async def search(self, *, query, num_results, start_published_date):
            return [
                _ExaResult(
                    title="HDFC Bank appoints new executive",
                    url="https://example.com/hdfc-management",
                    id="https://example.com/hdfc-management",
                    summary="HDFC Bank appoints a new executive.",
                    published_date=published.isoformat(),
                )
            ]

    connector = ExaSearchConnector(client=_Client(), max_results_per_query=20)

    results = await connector.fetch(company, time_window_days=30)

    assert len(results) == 1
    assert results[0].title == "HDFC Bank appoints new executive"
    assert results[0].snippet == "HDFC Bank appoints a new executive."


@pytest.mark.asyncio
async def test_exa_search_connector_logs_normalization_summary(caplog):
    company = CompanyContext(ticker="HDB", company_name="HDFC Bank Limited")

    portal_text = """HDFC Bank Limited (HDB) Latest Stock News & Headlines

### HDFC Bank delayed action in AT-1 bond mis-selling, former chair tells CNBC-TV18

Reuters 12d ago
"""

    class _Client:
        async def search(self, *, query, num_results, start_published_date):
            return [
                _ExaResult(
                    title="HDFC Bank Limited (HDB) Latest Stock News & Headlines",
                    url="https://finance.yahoo.com/quote/HDB/news/",
                    id="https://finance.yahoo.com/quote/HDB/news/",
                    text=portal_text,
                    published_date=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                ),
                _ExaResult(
                    title="HDFC Bank opens rural branches",
                    url="https://example.com/hdfc-rural-branches",
                    id="https://example.com/hdfc-rural-branches",
                    text="HDFC Bank expands its rural branch footprint.",
                    published_date=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                ),
            ]

    connector = ExaSearchConnector(client=_Client(), max_results_per_query=20)

    with caplog.at_level(logging.INFO, logger="data.news_pipeline.connectors"):
        results = await connector.fetch(company, time_window_days=30)

    assert len(results) == 2
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.message == "Exa connector normalized results"
    assert record.ticker == "HDB"
    assert record.raw_items_seen > 0
    assert record.portal_pages_detected > 0
    assert record.malformed_items_dropped == 0
    assert record.candidates_emitted == 2
