"""Offline news connector and extractor backed by immutable provider snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from app.observability.provider_archive import ProviderArchive
from data.news_pipeline.extractor import matches_company_aliases
from data.news_pipeline.models import CompanyContext, ExtractionResult, RawSearchResult


def _datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


class ReplayNewsConnector:
    """Convert an archived news payload into pipeline search records."""

    strict_replay = True

    def __init__(self, archive: ProviderArchive, content_hash: str | None) -> None:
        self.archive = archive
        self.content_hash = content_hash
        self.article_text_by_url: dict[str, str] = {}

    async def fetch(
        self, company: CompanyContext, *, time_window_days: int
    ) -> list[RawSearchResult]:
        del time_window_days
        if not self.content_hash:
            raise RuntimeError("replay snapshot missing for fetch_news")
        snapshot = self.archive.load(self.content_hash)
        if (
            snapshot.provider not in {"yfinance", "news_pipeline"}
            or snapshot.operation != "fetch_news"
        ):
            raise RuntimeError("replay snapshot does not match fetch_news")
        if not isinstance(snapshot.payload, list):
            raise TypeError("replay snapshot has an invalid news payload")
        records: list[RawSearchResult] = []
        for item in snapshot.payload:
            if not isinstance(item, dict):
                raise TypeError("replay news snapshot contains an invalid item")
            url = str(item.get("url") or item.get("article_link") or "").strip()
            title = str(item.get("title") or item.get("heading") or "").strip()
            if not url or not title:
                raise ValueError("replay news item requires url and title")
            content = str(item.get("content") or "").strip()
            if content:
                self.article_text_by_url[url] = content
            records.append(
                RawSearchResult(
                    ticker=company.ticker,
                    company_name=str(item.get("company_name") or company.company_name),
                    market=company.market,
                    title=title,
                    url=url,
                    source_domain=str(
                        item.get("source_domain") or urlparse(url).netloc
                    ).removeprefix("www."),
                    source_type=str(item.get("source_type") or "news"),
                    query_intent=str(item.get("query_intent") or "company_news"),
                    search_provider=str(item.get("search_provider") or "replay"),
                    snippet=str(item.get("summary") or item.get("snippet") or ""),
                    publish_time=_datetime(
                        item.get("published_date") or item.get("published_time")
                    ),
                )
            )
        return records


class ReplayArticleExtractor:
    """Use archived article content without resolving URLs over the network."""

    def __init__(self, article_text_by_url: dict[str, str]) -> None:
        self.article_text_by_url = article_text_by_url

    def extract(
        self,
        *,
        url: str,
        source_domain: str,
        company_name: str,
        ticker: str,
        snippet: str,
        source_type: str,
    ) -> ExtractionResult:
        del source_domain, source_type
        text = self.article_text_by_url.get(url) or snippet or None
        relevance = matches_company_aliases(text, company_name, ticker)
        return ExtractionResult(
            article_text=text,
            word_count=len(text.split()) if text else 0,
            extraction_status="full"
            if url in self.article_text_by_url
            else "snippet_only",
            paywall_detected=False,
            relevance_check=relevance,
        )
