from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import struct_time
from typing import Any
from urllib.parse import urlparse

import httpx
from app.config import settings
from app.observability.provider_archive import ProviderArchive
from data.news_pipeline.models import CompanyContext, RawSearchResult
from data.news_pipeline.query_templates import (
    QueryTemplateLibrary,
    build_queries_for_company,
    derive_company_aliases,
)
from data.news_pipeline.tinyfish_client import TinyFishSearchClient

logger = logging.getLogger(__name__)


def _httpx_limits() -> httpx.Limits:
    return httpx.Limits(
        max_connections=int(settings.HTTP_POOL_MAX_CONNECTIONS),
        max_keepalive_connections=int(settings.HTTP_POOL_MAX_KEEPALIVE_CONNECTIONS),
    )


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, struct_time):
        return datetime(*value[:6], tzinfo=UTC)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        for parser in (datetime.fromisoformat, parsedate_to_datetime):
            try:
                parsed = parser(stripped)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                continue
    return None


def _within_window(published_at: datetime | None, time_window_days: int) -> bool:
    if published_at is None:
        return True
    threshold = datetime.now(UTC) - timedelta(days=time_window_days)
    return published_at >= threshold


def _effective_child_publish_time(
    snippet: str, parent_publish_time: datetime | None
) -> datetime | None:
    if parent_publish_time is None:
        return None

    match = re.search(r"\b(\d+)\s*([mhdw])\s+ago\b", snippet.lower())
    if match is None:
        return parent_publish_time

    amount = int(match.group(1))
    unit = match.group(2)
    unit_to_delta = {
        "m": timedelta(minutes=amount),
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
        "w": timedelta(weeks=amount),
    }
    return datetime.now(UTC) - unit_to_delta[unit]


def _source_domain(url: str) -> str:
    domain = urlparse(url).netloc.lower()
    return domain.removeprefix("www.")


def _looks_like_portal_page(*, title: str, text: str) -> bool:
    lowered_title = title.lower()
    lowered_text = text.lower()
    portal_markers = ("latest stock news", "news & headlines", "headlines")
    return "###" in text and any(
        marker in lowered_title or marker in lowered_text for marker in portal_markers
    )


def _explode_portal_headlines(text: str) -> list[tuple[str, str]]:
    headlines: list[tuple[str, str]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("###"):
            if current_title:
                headlines.append((current_title, " ".join(current_lines).strip()))
            current_title = stripped.removeprefix("###").strip() or None
            current_lines = []
            continue
        if current_title and stripped:
            current_lines.append(stripped)

    if current_title:
        headlines.append((current_title, " ".join(current_lines).strip()))

    return headlines


class BaseNewsConnector:
    def __init__(self, *, timeout: float = 20.0) -> None:
        self.timeout = timeout

    async def _get(
        self, url: str, *, headers: dict[str, str] | None = None
    ) -> httpx.Response:
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            limits=_httpx_limits(),
        ) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response


def _matches_company_terms(text: str, company: CompanyContext) -> bool:
    lowered = text.lower()
    for alias in derive_company_aliases(company):
        normalized_alias = alias.strip().lower()
        if not normalized_alias:
            continue
        if re.search(
            rf"(?<![a-z0-9]){re.escape(normalized_alias)}(?![a-z0-9])", lowered
        ):
            return True
    return False


def _item_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


class TinyFishSearchConnector:
    def __init__(
        self,
        *,
        client: TinyFishSearchClient | Any | None = None,
        max_results_per_query: int | None = None,
        archive: ProviderArchive | None = None,
    ) -> None:
        self.client = client or TinyFishSearchClient(
            api_key=str(settings.TINYFISH_API_KEY or ""),
            base_url=settings.TINYFISH_SEARCH_URL,
            timeout=float(settings.TINYFISH_SEARCH_TIMEOUT),
            archive=archive or ProviderArchive(Path(".finai")),
        )
        self.max_results_per_query = max_results_per_query or int(
            settings.TINYFISH_MAX_RESULTS_PER_QUERY
        )

    async def fetch(
        self, company: CompanyContext, *, time_window_days: int
    ) -> list[RawSearchResult]:
        if isinstance(self.client, TinyFishSearchClient) and not self.client.api_key:
            logger.warning("TINYFISH_API_KEY is not configured; skipping news search")
            logger.info(
                "TinyFish connector normalized results",
                extra={
                    "ticker": company.ticker,
                    "raw_items_seen": 0,
                    "portal_pages_detected": 0,
                    "malformed_items_dropped": 0,
                    "candidates_emitted": 0,
                },
            )
            return []

        queries = build_queries_for_company(
            company=company,
            intents=list(QueryTemplateLibrary.keys()),
            time_window_days=time_window_days,
        )
        start_published_date = datetime.now(UTC) - timedelta(days=time_window_days)
        results: list[RawSearchResult] = []
        seen_result_keys: set[str] = set()
        raw_items_seen = 0
        portal_pages_detected = 0
        malformed_items_dropped = 0
        candidates_emitted = 0

        for query_spec in queries:
            search_results = await self.client.search(
                query=str(query_spec["query"]),
                num_results=self.max_results_per_query,
                start_published_date=start_published_date,
            )
            for item in search_results:
                raw_items_seen += 1
                title = str(_item_value(item, "title") or "").strip()
                article_url = str(_item_value(item, "url") or "").strip()
                if not title or not article_url:
                    malformed_items_dropped += 1
                    continue
                snippet = str(
                    _item_value(item, "snippet")
                    or _item_value(item, "text")
                    or _item_value(item, "summary")
                    or ""
                ).strip()
                candidate_entries = [(title, snippet)]
                if _looks_like_portal_page(title=title, text=snippet):
                    portal_pages_detected += 1
                    exploded_entries = _explode_portal_headlines(snippet)
                    if exploded_entries:
                        candidate_entries = exploded_entries
                    else:
                        malformed_items_dropped += 1
                        continue
                elif not _matches_company_terms(f"{title} {snippet}", company):
                    continue

                publish_time = _parse_datetime(
                    _item_value(item, "published_date")
                    or _item_value(item, "publishedDate")
                )
                if candidate_entries == [(title, snippet)] and not _within_window(
                    publish_time, time_window_days
                ):
                    continue
                author = str(_item_value(item, "author") or "").strip() or None
                for candidate_title, candidate_snippet in candidate_entries:
                    candidate_publish_time = publish_time
                    if candidate_title != title:
                        candidate_publish_time = _effective_child_publish_time(
                            candidate_snippet, publish_time
                        )
                    if not _within_window(candidate_publish_time, time_window_days):
                        continue
                    if not _matches_company_terms(
                        f"{candidate_title} {candidate_snippet}", company
                    ):
                        continue
                    result_key = (
                        article_url
                        if candidate_title == title
                        else (f"{article_url}#{candidate_title}")
                    )
                    if result_key in seen_result_keys:
                        continue
                    seen_result_keys.add(result_key)
                    candidates_emitted += 1
                    results.append(
                        RawSearchResult(
                            ticker=company.ticker,
                            company_name=company.company_name,
                            market=company.market,
                            title=candidate_title,
                            url=article_url,
                            original_url=article_url,
                            source_domain=_source_domain(article_url),
                            source_type="search",
                            query_intent=str(query_spec["intent"]),
                            search_provider="tinyfish",
                            snippet=candidate_snippet,
                            author=author,
                            publish_time=candidate_publish_time,
                        )
                    )
        logger.info(
            "TinyFish connector normalized results",
            extra={
                "ticker": company.ticker,
                "raw_items_seen": raw_items_seen,
                "portal_pages_detected": portal_pages_detected,
                "malformed_items_dropped": malformed_items_dropped,
                "candidates_emitted": candidates_emitted,
            },
        )
        return results
