"""Materialize news payloads from the vector DB.

This module is responsible for reading existing news chunks for a ticker from
the vector DB and converting them to the lightweight article dicts expected by
the rest of the pipeline.
"""

from __future__ import annotations

from typing import Any

from app.core.node_resources import resources
from agents.financial.data.news.dedupe import dedupe_key_from_payload
from agents.financial.data.news.metrics import sort_articles_newest_first
from agents.financial.data.symbol_resolution import (
    RankedMatchPolicy,
    canonicalize_ticker,
    should_accept_ranked_symbol_match,
    ticker_variants,
)


def _resolve_typo_ticker_candidates(ticker: str) -> list[str]:
    candidate = canonicalize_ticker(ticker)
    if not candidate:
        return []

    ranked_search = getattr(resources.sql_db, "search_instruments_ranked", None)
    if not callable(ranked_search):
        return []

    try:
        ranked_raw = ranked_search(
            query=candidate,
            limit=3,
            exchange="NSE",
            segment="EQ",
        )
    except Exception:  # noqa: BLE001
        return []

    ranked = ranked_raw if isinstance(ranked_raw, list) else []
    accepted, symbol = should_accept_ranked_symbol_match(
        [row for row in ranked if isinstance(row, dict)],
        policy=RankedMatchPolicy(min_top_score=0.85, min_gap=0.1),
    )
    if not accepted or symbol is None:
        return []
    return ticker_variants(symbol)


def load_news_from_vector_db(
    ticker: str,
    *,
    limit: int,
) -> list[dict[str, Any]] | None:
    """Load recent news for a ticker from the vector DB.

    Behavior-preserving extraction from `data_fetch_node._load_news_from_vector_db`.
    """

    if not isinstance(ticker, str) or not ticker.strip():
        return None

    vector_db = resources.vector_db
    variants = ticker_variants(ticker)
    chunks = vector_db.list_recent_by_tickers(variants, limit=max(int(limit), 1))

    if not chunks:
        typo_variants = _resolve_typo_ticker_candidates(ticker)
        if typo_variants:
            chunks = vector_db.list_recent_by_tickers(
                typo_variants, limit=max(int(limit), 1)
            )

    if not chunks:
        return None

    articles: list[dict[str, Any]] = []
    seen: set[str] = set()

    for chunk in chunks:
        metadata = getattr(chunk, "metadata", {}) or {}
        text = getattr(chunk, "text", "")
        if not isinstance(text, str) or not text.strip():
            continue

        payload = dict(metadata)
        dedupe = dedupe_key_from_payload(payload)
        if dedupe and dedupe in seen:
            continue
        if dedupe:
            seen.add(dedupe)

        articles.append(
            {
                "ticker": (
                    str(chunk.ticker).strip().upper()
                    if hasattr(chunk, "ticker") and chunk.ticker
                    else str(payload.get("ticker", ticker)).strip().upper()
                ),
                "title": str(payload.get("title", "")),
                "summary": text.strip(),
                "content": "",
                "source": str(payload.get("source", "")),
                "published_date": str(payload.get("published_date", "")),
                "url": str(payload.get("url", "")),
                "link": str(payload.get("url", payload.get("link", ""))),
            }
        )
        if len(articles) >= max(int(limit), 1):
            break

    if not articles:
        return None

    sort_articles_newest_first(articles)
    return articles
