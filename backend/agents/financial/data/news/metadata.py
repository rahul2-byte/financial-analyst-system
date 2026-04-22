"""Metadata builders for storing and retrieving news in the vector DB."""

from __future__ import annotations

from typing import Any

from agents.financial.data.news.dedupe import sha256


def build_news_chunk_metadata(
    article: dict[str, Any], ticker: str | None
) -> dict[str, Any]:
    """Build the metadata dict passed to vector-db chunk upserts.

    Behavior-preserving extraction from `data_fetch_node._build_news_chunk_metadata`.

    Inputs:
    - `article`: normalized article dict (may contain many optional keys).
    - `ticker`: fallback ticker.

    Output:
    - metadata dict containing stable hashes + a dedupe key plus selected optional
      pipeline fields.
    """

    title = str(article.get("title", ""))
    content = str(article.get("content", ""))
    title_hash = str(article.get("title_hash") or sha256(title))
    content_hash = str(article.get("content_hash") or sha256(content))
    article_hash = str(
        article.get("article_hash") or sha256(f"{title_hash}:{content_hash}")
    )
    dedupe_key = str(
        article.get("dedupe_key")
        or article.get("canonical_url")
        or article.get("url")
        or article_hash
    )

    metadata: dict[str, Any] = {
        "ticker": article.get("ticker", ticker or "UNKNOWN"),
        "source": article.get("source", "RSS"),
        "url": article.get("url", ""),
        "published_date": str(article.get("published_date", "")),
        "title_hash": title_hash,
        "content_hash": content_hash,
        "article_hash": article_hash,
        "dedupe_key": dedupe_key,
    }

    for key in (
        "canonical_url",
        "resolved_url",
        "original_url",
        "source_domain",
        "source_type",
        "source_tier",
        "query_objective",
        "query_variant",
        "intent_type",
        "query_intent",
        "search_provider",
        "search_rank",
        "is_trusted_domain",
        "timeframe",
        "run_id",
        "fetched_at",
        "original_blocked_url",
        "quality_score",
        "paywall_detected",
        "extraction_status",
        "relevance_check",
        "is_duplicate",
        "cluster_id",
        "pipeline_version",
    ):
        if key in article:
            metadata[key] = article.get(key)

    if "intent_type" not in metadata and "query_intent" in metadata:
        metadata["intent_type"] = metadata["query_intent"]

    return metadata
