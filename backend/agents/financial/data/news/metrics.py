"""Coverage, freshness, and cache-index summaries for news."""

from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import urlparse

import pandas as pd

from agents.financial.data.news.dedupe import (
    EPOCH_UTC,
    article_dedupe_key,
    parse_iso_datetime,
)
from agents.shared.utils import derive_news_freshness_score


def parse_timestamp(value: Any):
    """Parse a timestamp string using pandas (legacy behavior).

    Returns a python datetime or None.
    """

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if hasattr(value, "tzinfo"):
        # Covers datetime; avoids importing datetime directly here.
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(candidate):
        return None
    return candidate.to_pydatetime()


def resolve_source_domain(article: dict[str, Any]) -> str:
    """Derive a best-effort source domain from URL-ish fields."""

    candidate = (
        article.get("source_domain")
        or article.get("canonical_url")
        or article.get("url")
        or article.get("link")
    )
    if not isinstance(candidate, str) or not candidate.strip():
        return ""
    parsed = urlparse(candidate)
    if parsed.netloc:
        domain = parsed.netloc.lower()
        return domain[4:] if domain.startswith("www.") else domain
    return candidate.strip().lower()


def is_trusted_article(article: dict[str, Any]) -> bool:
    """Return True if article is from a trusted domain (legacy heuristic)."""

    explicit_value = article.get("is_trusted_domain")
    if isinstance(explicit_value, bool):
        return explicit_value
    source_tier = article.get("source_tier")
    if isinstance(source_tier, int):
        return source_tier <= 2
    return False


def is_open_web_article(article: dict[str, Any]) -> bool:
    """Return True if article is not a filing and has a URL."""

    source_type = article.get("source_type")
    if isinstance(source_type, str) and source_type.strip():
        return source_type.strip().lower() != "filing"
    return bool(article.get("url") or article.get("link"))


def _max_dt(values: Iterable[Any]):
    dts = [value for value in values if value is not None]
    return max(dts, default=None)


def build_news_cache_summary(
    payload: list[dict[str, Any]],
    *,
    chunk_count: int,
    planned_intent_types: tuple[str, ...],
    freshness_threshold: float,
) -> dict[str, Any]:
    """Build the metadata stored in `sql_db.update_cache_index(..., dataset='news')`.

    This is a behavior-preserving extraction from `data_fetch_node._build_news_cache_summary`.
    Callers must pass `planned_intent_types` and the same freshness threshold used previously.
    """

    dedupe_keys = {
        dedupe for article in payload if (dedupe := article_dedupe_key(article))
    }
    covered_intent_types = sorted(
        {
            article["intent_type"].strip()
            for article in payload
            if isinstance(article.get("intent_type"), str)
            and article["intent_type"].strip()
        }
    )
    query_variants = sorted(
        {
            article["query_variant"].strip()
            for article in payload
            if isinstance(article.get("query_variant"), str)
            and article["query_variant"].strip()
        }
    )
    timeframe_values = sorted(
        {
            article["timeframe"].strip()
            for article in payload
            if isinstance(article.get("timeframe"), str)
            and article["timeframe"].strip()
        }
    )

    latest_published_at = _max_dt(
        parse_timestamp(article.get("published_date") or article.get("published"))
        for article in payload
    )
    latest_fetch_at = _max_dt(
        parse_timestamp(article.get("fetched_at")) for article in payload
    )

    coverage_by_intent: dict[str, dict[str, int]] = {}
    for intent_type in covered_intent_types:
        intent_articles = [
            article
            for article in payload
            if str(article.get("intent_type", "")).strip() == intent_type
        ]
        intent_dedupe_keys = {
            dedupe
            for article in intent_articles
            if (dedupe := article_dedupe_key(article))
        }
        coverage_by_intent[intent_type] = {
            "article_count": len(intent_articles),
            "deduped_article_count": len(intent_dedupe_keys),
            "trusted_article_count": sum(
                1 for a in intent_articles if is_trusted_article(a)
            ),
            "open_web_article_count": sum(
                1 for a in intent_articles if is_open_web_article(a)
            ),
        }

    timeframe: str | None = None
    if len(timeframe_values) == 1:
        timeframe = timeframe_values[0]
    elif timeframe_values:
        timeframe = ",".join(timeframe_values)

    freshness_score = derive_news_freshness_score(payload, stale_after_days=2)
    return {
        "last_fetch_at": (
            latest_fetch_at.isoformat() if latest_fetch_at is not None else None
        ),
        "latest_published_at": (
            latest_published_at.isoformat() if latest_published_at is not None else None
        ),
        "article_count": len(payload),
        "deduped_article_count": len(dedupe_keys),
        "trusted_article_count": sum(
            1 for article in payload if is_trusted_article(article)
        ),
        "open_web_article_count": sum(
            1 for article in payload if is_open_web_article(article)
        ),
        "covered_intent_types": covered_intent_types,
        "missing_intent_types": [
            intent
            for intent in planned_intent_types
            if intent not in covered_intent_types
        ],
        "query_variants": query_variants,
        "coverage_by_intent": coverage_by_intent,
        "timeframe": timeframe,
        "fresh_enough": freshness_score >= freshness_threshold,
        "vector_ready": chunk_count > 0,
        "chunk_count": chunk_count,
    }


def sort_articles_newest_first(articles: list[dict[str, Any]]) -> None:
    """In-place sort: newest published_date first (legacy behavior)."""

    articles.sort(
        key=lambda a: parse_iso_datetime(a.get("published_date")) or EPOCH_UTC,
        reverse=True,
    )
