"""News pipeline concurrency: rate-limit-aware quota, parallel queries/extraction."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta

import pytest
from app.core.quota import QuotaExceeded, RequestQuota
from data.news_pipeline.connectors import TinyFishSearchConnector
from data.news_pipeline.models import CompanyContext, ExtractionResult, RawSearchResult
from data.news_pipeline.runner import NewsPipelineRunner

COMPANY = CompanyContext(
    ticker="HDFCBANK", company_name="HDFC BANK LTD", nse_symbol="HDFCBANK"
)


@pytest.mark.asyncio
async def test_quota_acquire_waits_instead_of_raising_and_respects_rate(tmp_path):
    quota = RequestQuota(tmp_path / "q.sqlite3", per_second=2)
    with pytest.raises(QuotaExceeded) as info:
        for _ in range(3):
            quota.reserve("p")
    assert info.value.retry_after is not None and info.value.retry_after > 0
    quota.close()

    quota = RequestQuota(tmp_path / "q2.sqlite3", per_second=2)
    stamps: list[float] = []

    async def one() -> None:
        await quota.acquire("p")  # never raises while only the per-second cap binds
        stamps.append(time.monotonic())

    started = time.monotonic()
    await asyncio.gather(*(one() for _ in range(5)))
    stamps.sort()
    assert len(stamps) == 5
    # No 1 second window may hold more than 2 requests.
    for index in range(len(stamps) - 2):
        assert stamps[index + 2] - stamps[index] >= 0.99
    assert time.monotonic() - started >= 1.9  # 5 requests at 2/s need ~2 s


@pytest.mark.asyncio
async def test_quota_acquire_still_fails_closed_on_minute_budget(tmp_path):
    quota = RequestQuota(tmp_path / "q.sqlite3", per_second=10, per_minute=1)
    await quota.acquire("p")
    with pytest.raises(QuotaExceeded, match="minute"):
        await quota.acquire("p")


class _OrderedClient:
    """Each query sleeps a different time; first query is the slowest."""

    def __init__(self, delays: list[float]) -> None:
        self.delays = delays
        self.spans: list[tuple[float, float]] = []
        self.calls = 0

    async def search(self, *, query, num_results, start_published_date):
        del num_results, start_published_date
        index = self.calls
        self.calls += 1
        began = time.monotonic()
        await asyncio.sleep(self.delays[index % len(self.delays)])
        self.spans.append((began, time.monotonic()))
        published = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        return [
            {
                "title": f"HDFC Bank news {index}",
                "url": f"https://example.com/{index}",
                "snippet": "HDFC Bank update",
                "published_date": published,
            },
            {  # same URL from every query: must dedupe to the first query's copy
                "title": "HDFC Bank shared story",
                "url": "https://example.com/shared",
                "snippet": f"HDFC Bank from query {index}",
                "published_date": published,
            },
        ]


@pytest.mark.asyncio
async def test_queries_overlap_and_results_keep_query_order():
    delays = [0.3, 0.2, 0.1]
    client = _OrderedClient(delays)
    connector = TinyFishSearchConnector(client=client, max_queries_per_run=3)

    started = time.monotonic()
    results = await connector.fetch(COMPANY, time_window_days=30)
    elapsed = time.monotonic() - started

    assert elapsed < sum(delays) * 0.8  # wall time ~ max, not sum
    assert len(client.spans) == 3
    assert max(s[0] for s in client.spans) < min(s[1] for s in client.spans)
    # Same output as running the queries one after another: query order, with
    # the shared URL kept from the first query.
    assert [r.url for r in results] == [
        "https://example.com/0",
        "https://example.com/shared",
        "https://example.com/1",
        "https://example.com/2",
    ]
    shared = next(r for r in results if r.url.endswith("shared"))
    assert shared.snippet == "HDFC Bank from query 0"


class _Connector:
    def __init__(self, results):
        self.results = results

    async def fetch(self, company, *, time_window_days):
        return list(self.results)


class _SleepExtractor:
    def __init__(self) -> None:
        self.spans: list[tuple[float, float]] = []

    def extract(self, **kwargs):
        began = time.monotonic()
        time.sleep(0.2)
        self.spans.append((began, time.monotonic()))
        return ExtractionResult(
            article_text="HDFC Bank body " * 40,
            word_count=120,
            extraction_status="full",
            paywall_detected=False,
            relevance_check=True,
        )


def _raw(index: int) -> RawSearchResult:
    return RawSearchResult(
        ticker="HDFCBANK",
        company_name="HDFC BANK LTD",
        market="IN",
        title=f"HDFC Bank story {index}",
        url=f"https://www.reuters.com/a{index}",
        original_url=f"https://www.reuters.com/a{index}",
        source_domain="reuters.com",
        source_type="search",
        query_intent="company_news",
        search_provider="tinyfish",
        snippet=f"HDFC Bank story number {index}",
        publish_time=datetime.now(UTC) - timedelta(days=1, minutes=index),
    )


@pytest.mark.asyncio
async def test_extractions_overlap_and_order_matches_sequential_run():
    raws = [_raw(i) for i in range(8)]

    def runner(extractor, concurrency):
        from app.config import settings

        settings.NEWS_EXTRACTION_CONCURRENCY = concurrency
        return NewsPipelineRunner(
            connectors=[_Connector(raws)],
            extractor=extractor,
            apply_quality_filter=False,
            total_timeout_seconds=30,
            extraction_timeout_seconds=5,
        )

    from app.config import settings

    original = settings.NEWS_EXTRACTION_CONCURRENCY
    try:
        sequential = runner(_SleepExtractor(), 1)
        t0 = time.monotonic()
        seq_records = await sequential.run(company=COMPANY, time_window_days=30)
        seq_elapsed = time.monotonic() - t0

        extractor = _SleepExtractor()
        parallel = runner(extractor, 8)
        t0 = time.monotonic()
        par_records = await parallel.run(company=COMPANY, time_window_days=30)
        par_elapsed = time.monotonic() - t0
    finally:
        settings.NEWS_EXTRACTION_CONCURRENCY = original

    assert seq_elapsed >= 8 * 0.2 * 0.9
    assert par_elapsed < seq_elapsed / 2
    assert max(s[0] for s in extractor.spans) < min(s[1] for s in extractor.spans)
    assert [r.url for r in par_records] == [r.url for r in seq_records]
    assert [r.canonical_url for r in par_records] == [
        r.canonical_url for r in seq_records
    ]
    # Provenance preserved on every record.
    assert all(r.retrieval_time is not None and r.url for r in par_records)
