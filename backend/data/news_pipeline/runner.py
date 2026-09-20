from __future__ import annotations

import asyncio
import contextvars
import functools
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Protocol, TypeVar

from app.config import settings
from app.core.observability import observe, run_context
from data.news_pipeline.connectors import TinyFishSearchConnector, UpstoxNewsConnector
from data.news_pipeline.extractor import ArticleExtractor
from data.news_pipeline.models import (
    CompanyContext,
    NewsPipelineRecord,
    RawSearchResult,
)
from data.news_pipeline.normalize import DuplicateDetector, URLNormalizer
from data.news_pipeline.quality import QualityScorer, SourceClassifier
from data.news_pipeline.query_templates import (
    QueryTemplateLibrary,
    build_queries_for_company,
    infer_query_intent,
)


class NewsConnector(Protocol):
    async def fetch(
        self, company: CompanyContext, *, time_window_days: int
    ) -> list[RawSearchResult]: ...


Result = TypeVar("Result")


async def _run_sync(
    function: Callable[..., Result], /, *args: Any, **kwargs: Any
) -> Result:
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = loop.run_in_executor(
            executor,
            contextvars.copy_context().run,
            functools.partial(function, *args, **kwargs),
        )
        while not future.done():
            await asyncio.sleep(0.001)
        return future.result()


class NewsPipelineRunner:
    def __init__(
        self,
        *,
        connectors: list[NewsConnector] | None = None,
        extractor: ArticleExtractor | None = None,
        max_articles_per_company: int = 50,
        min_quality_score: float = 40.0,
        apply_quality_filter: bool = True,
        pipeline_version: str = "1.0.0",
    ) -> None:
        if connectors is None:
            self.connectors = [TinyFishSearchConnector()]
            if settings.UPSTOX_ACCESS_TOKEN:
                self.connectors.append(UpstoxNewsConnector())
        else:
            self.connectors = connectors
        self.extractor = extractor or ArticleExtractor()
        self.max_articles_per_company = max_articles_per_company
        self.min_quality_score = min_quality_score
        self.apply_quality_filter = apply_quality_filter
        self.pipeline_version = pipeline_version
        self.last_run_stats: dict[str, Any] = {}
        self.url_normalizer = URLNormalizer()
        self.duplicate_detector = DuplicateDetector()

    @observe(name="Data:FetchNewsPipeline", as_type="span")
    async def run(
        self, *, company: CompanyContext, time_window_days: int
    ) -> list[NewsPipelineRecord]:
        build_queries_for_company(
            company=company,
            intents=list(QueryTemplateLibrary.keys()),
            time_window_days=time_window_days,
        )
        connector_results = await asyncio.gather(
            *(
                connector.fetch(company, time_window_days=time_window_days)
                for connector in self.connectors
            ),
            return_exceptions=True,
        )
        raw_results: list[RawSearchResult] = []
        connector_failures = 0
        connector_failure_reasons: list[str] = []
        for item in connector_results:
            if isinstance(item, list):
                raw_results.extend(item)
            elif isinstance(item, Exception):
                connector_failures += 1
                connector_failure_reasons.append(type(item).__name__)
                if any(
                    getattr(connector, "strict_replay", False)
                    for connector in self.connectors
                ):
                    raise item

        semaphore = asyncio.Semaphore(5)

        async def process_result(raw: RawSearchResult) -> NewsPipelineRecord | None:
            async with semaphore:
                source_tier = SourceClassifier.classify(raw.source_domain)
                if self.apply_quality_filter and source_tier == 4:
                    return None
                canonical_url = await _run_sync(
                    self.url_normalizer.resolve_canonical, raw.url
                )
                # Keep synchronous parsing and downloads off the event loop.
                extraction = await _run_sync(
                    self.extractor.extract,
                    url=raw.url,
                    source_domain=raw.source_domain,
                    company_name=company.company_name,
                    ticker=company.ticker,
                    snippet=raw.snippet,
                    source_type=raw.source_type,
                )
                record = NewsPipelineRecord(
                    ticker=raw.ticker,
                    company_name=raw.company_name,
                    market=raw.market,
                    url=raw.url,
                    canonical_url=canonical_url,
                    title=raw.title,
                    author=raw.author,
                    snippet=raw.snippet,
                    article_text=extraction.article_text,
                    word_count=extraction.word_count,
                    publish_time=raw.publish_time,
                    retrieval_time=datetime.now(UTC),
                    source_domain=raw.source_domain,
                    source_type=raw.source_type,
                    source_tier=source_tier,
                    paywall_detected=extraction.paywall_detected,
                    extraction_status=extraction.extraction_status,
                    quality_score=0.0,
                    relevance_check=extraction.relevance_check,
                    is_duplicate=False,
                    cluster_id=None,
                    query_intent=raw.query_intent
                    or infer_query_intent(raw.title, raw.snippet, raw.source_type),
                    search_provider=raw.search_provider,
                    pipeline_version=self.pipeline_version,
                )
                return record

        extracted = await asyncio.gather(
            *(process_result(raw) for raw in raw_results),
            return_exceptions=True,
        )
        extraction_failures = sum(isinstance(item, Exception) for item in extracted)
        records = [item for item in extracted if isinstance(item, NewsPipelineRecord)]
        deduped = self.duplicate_detector.mark_duplicates(records)

        scored: list[NewsPipelineRecord] = []
        for record in deduped:
            quality_score = QualityScorer.score(
                source_tier=record.source_tier,
                extraction_status=record.extraction_status,
                publish_time=record.publish_time,
                relevance_check=record.relevance_check,
                word_count=record.word_count,
                is_duplicate=record.is_duplicate,
            )
            updated = replace(record, quality_score=quality_score)
            if (
                not self.apply_quality_filter
                or updated.quality_score >= self.min_quality_score
            ):
                scored.append(updated)

        scored.sort(key=lambda item: item.quality_score, reverse=True)
        final_list = scored[: self.max_articles_per_company]

        self.last_run_stats = {
            "quality_filtering": self.apply_quality_filter,
            "raw_count": len(raw_results),
            "deduped_count": len(deduped),
            "quality_filtered_count": len(deduped) - len(scored),
            "retained_count": len(final_list),
            "connector_failures": connector_failures,
            "connector_failure_reasons": connector_failure_reasons,
            "query_failures": sum(
                int(getattr(connector, "last_run_stats", {}).get("query_failures", 0))
                for connector in self.connectors
            ),
            "extraction_failures": extraction_failures,
            "status": (
                "available"
                if final_list
                else "degraded"
                if raw_results or connector_failures
                else "empty"
            ),
        }

        run_context.update_current_span(
            metadata={
                "raw_results": len(raw_results),
                "deduped": len(deduped),
                "final_scored": len(final_list),
            }
        )
        return final_list
