from __future__ import annotations

import asyncio
import contextvars
import functools
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from time import monotonic
from typing import Any, Protocol, TypeVar

from app.config import settings
from app.core.observability import observe, run_context
from data.news_pipeline.connectors import TinyFishSearchConnector, UpstoxNewsConnector
from data.news_pipeline.extractor import ArticleExtractor, matches_company_aliases
from data.news_pipeline.models import (
    CompanyContext,
    ExtractionResult,
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
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="news-pipeline")
    concurrent_future = executor.submit(
        contextvars.copy_context().run,
        functools.partial(function, *args, **kwargs),
    )
    while not concurrent_future.done():
        await asyncio.sleep(0.001)
    executor.shutdown(wait=False)
    return concurrent_future.result()


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
        total_timeout_seconds: float | None = None,
        extraction_timeout_seconds: float | None = None,
        max_extractions: int | None = None,
        allow_degraded_fallback: bool = True,
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
        self.total_timeout_seconds = total_timeout_seconds
        self.extraction_timeout_seconds = extraction_timeout_seconds
        self.max_extractions = max_extractions
        self.allow_degraded_fallback = allow_degraded_fallback
        self.last_run_stats: dict[str, Any] = {}
        self.url_normalizer = URLNormalizer()
        self.duplicate_detector = DuplicateDetector()

    @observe(name="Data:FetchNewsPipeline", as_type="span")
    async def run(
        self, *, company: CompanyContext, time_window_days: int
    ) -> list[NewsPipelineRecord]:
        started = monotonic()
        total_timeout = self.total_timeout_seconds or float(
            settings.NEWS_PIPELINE_TOTAL_TIMEOUT
        )
        extraction_timeout = self.extraction_timeout_seconds or float(
            settings.NEWS_EXTRACTION_TIMEOUT
        )
        max_extractions = self.max_extractions or int(settings.NEWS_MAX_EXTRACTIONS)
        build_queries_for_company(
            company=company,
            intents=list(QueryTemplateLibrary.keys()),
            time_window_days=time_window_days,
        )
        timeout = False
        connector_started = monotonic()
        remaining = max(0.0, total_timeout - (monotonic() - started))
        try:
            connector_results = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        connector.fetch(company, time_window_days=time_window_days)
                        for connector in self.connectors
                    ),
                    return_exceptions=True,
                ),
                timeout=remaining,
            )
        except TimeoutError:
            connector_results = []
            timeout = True
        connector_elapsed_ms = round((monotonic() - connector_started) * 1000, 2)
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
        extraction_started = 0
        drop_reasons: dict[str, int] = {}

        def dropped(reason: str) -> None:
            drop_reasons[reason] = drop_reasons.get(reason, 0) + 1

        async def process_result(raw: RawSearchResult) -> NewsPipelineRecord | None:
            nonlocal extraction_started
            async with semaphore:
                if extraction_started >= max_extractions:
                    dropped("extraction_limit")
                    return None
                extraction_started += 1
                source_tier = SourceClassifier.classify(raw.source_domain)
                if self.apply_quality_filter and source_tier == 4:
                    dropped("blocked_source")
                    return None
                canonical_url = self.url_normalizer.normalize(raw.url)
                if raw.search_provider == "upstox":
                    article_text = raw.snippet.strip() or None
                    extraction = ExtractionResult(
                        article_text=article_text,
                        word_count=len(article_text.split()) if article_text else 0,
                        extraction_status="snippet_only",
                        paywall_detected=False,
                        relevance_check=matches_company_aliases(
                            f"{raw.title} {raw.snippet}",
                            company.company_name,
                            company.ticker,
                        ),
                    )
                else:
                    # Keep synchronous parsing and downloads off the event loop.
                    remaining = total_timeout - (monotonic() - started)
                    extraction = await asyncio.wait_for(
                        _run_sync(
                            self.extractor.extract,
                            url=raw.url,
                            source_domain=raw.source_domain,
                            company_name=company.company_name,
                            ticker=company.ticker,
                            snippet=raw.snippet,
                            source_type=raw.source_type,
                        ),
                        timeout=max(0.01, min(extraction_timeout, remaining)),
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
                    relevance_check=extraction.relevance_check
                    or (
                        extraction.extraction_status != "failed"
                        and bool(extraction.article_text)
                        and matches_company_aliases(
                            f"{raw.title} {raw.snippet}",
                            company.company_name,
                            company.ticker,
                        )
                    ),
                    is_duplicate=False,
                    cluster_id=None,
                    query_intent=raw.query_intent
                    or infer_query_intent(raw.title, raw.snippet, raw.source_type),
                    search_provider=raw.search_provider,
                    pipeline_version=self.pipeline_version,
                )
                return record

        extraction_started_at = monotonic()
        extracted = await asyncio.gather(
            *(process_result(raw) for raw in raw_results),
            return_exceptions=True,
        )
        extraction_elapsed_ms = round((monotonic() - extraction_started_at) * 1000, 2)
        extraction_failures = sum(isinstance(item, Exception) for item in extracted)
        timeout = timeout or any(
            isinstance(item, (TimeoutError, asyncio.TimeoutError)) for item in extracted
        )
        if extraction_failures:
            drop_reasons["extraction_failure"] = extraction_failures
        extraction_timeouts = sum(
            isinstance(item, (TimeoutError, asyncio.TimeoutError)) for item in extracted
        )
        if extraction_timeouts:
            drop_reasons["extraction_timeout"] = extraction_timeouts
        records = [item for item in extracted if isinstance(item, NewsPipelineRecord)]
        dedupe_started_at = monotonic()
        deduped = self.duplicate_detector.mark_duplicates(records)
        dedupe_elapsed_ms = round((monotonic() - dedupe_started_at) * 1000, 2)

        scored: list[NewsPipelineRecord] = []
        safe_candidates: list[NewsPipelineRecord] = []
        below_threshold_count = 0
        for record in deduped:
            if self.apply_quality_filter and not record.relevance_check:
                dropped("irrelevant_record")
                continue
            quality_score = QualityScorer.score(
                source_tier=record.source_tier,
                extraction_status=record.extraction_status,
                publish_time=record.publish_time,
                relevance_check=record.relevance_check,
                word_count=record.word_count,
                is_duplicate=record.is_duplicate,
            )
            updated = replace(record, quality_score=quality_score)
            if self.apply_quality_filter and record.relevance_check:
                safe_candidates.append(updated)
            if (
                not self.apply_quality_filter
                or updated.quality_score >= self.min_quality_score
            ):
                scored.append(updated)
            else:
                below_threshold_count += 1

        scored.sort(key=lambda item: item.quality_score, reverse=True)
        degraded_fallback_count = 0
        if (
            self.apply_quality_filter
            and self.allow_degraded_fallback
            and not scored
            and safe_candidates
        ):
            safe_candidates.sort(key=lambda item: item.quality_score, reverse=True)
            final_list = safe_candidates[: self.max_articles_per_company]
            degraded_fallback_count = len(final_list)
        else:
            final_list = scored[: self.max_articles_per_company]

        self.last_run_stats = {
            "quality_filtering": self.apply_quality_filter,
            "raw_count": len(raw_results),
            "deduped_count": len(deduped),
            "quality_filtered_count": len(deduped) - len(scored),
            "below_threshold_count": below_threshold_count,
            "retained_count": len(final_list),
            "degraded_fallback_count": degraded_fallback_count,
            "timeout": timeout,
            "elapsed_ms": round((monotonic() - started) * 1000, 2),
            "connector_elapsed_ms": connector_elapsed_ms,
            "extraction_elapsed_ms": extraction_elapsed_ms,
            "dedupe_elapsed_ms": dedupe_elapsed_ms,
            "drop_reasons": drop_reasons,
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
        if timeout or degraded_fallback_count:
            self.last_run_stats["status"] = "degraded"

        run_context.update_current_span(
            metadata={
                "raw_results": len(raw_results),
                "deduped": len(deduped),
                "final_scored": len(final_list),
            }
        )
        return final_list
