"""Persistence helpers for financial data nodes.

This module owns side effects for persisting fetched/materialized datasets.

Behavior-preserving note:
The writes performed here must remain equivalent to the legacy `_store_data` logic
that previously lived in `agents.financial.data.data_fetch_node`.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

import pandas as pd

from app.core.node_resources import resources
from app.core.observability import observe
from data.schemas.market import OHLCVData

from agents.financial.data.news.metadata import build_news_chunk_metadata
from agents.financial.data.news.metrics import build_news_cache_summary
from agents.financial.data.news.dedupe import dedupe_articles_by_url

logger = logging.getLogger(__name__)


class PersistOutcome(TypedDict):
    """Outcome of a persistence attempt."""

    ok: bool
    error: str | None


@observe(name="Data:PersistDataset", as_type="span")
def persist_dataset(
    *,
    dataset: str,
    payload: Any,
    ticker: str | None,
    payload_by_symbol: dict[str, Any] | None = None,
    planned_news_intent_types: tuple[str, ...] | None = None,
    news_freshness_threshold: float | None = None,
) -> PersistOutcome:
    """Persist a dataset payload to structured storage and/or vector DB.

    Side effects (legacy behavior):
    - OHLCV: saves rows into SQL and updates cache index per symbol.
    - Fundamentals: upserts fundamentals and updates cache index per symbol.
    - Macro: upserts macro indicators and updates cache index for "MACRO".
    - News: chunks + upserts into vector DB and updates per-ticker cache index.

    Notes:
    - This function intentionally catches exceptions and returns a failure
      outcome; callers decide how to surface failures.
    - News cache summary requires the planned intent types and freshness
      threshold used by the caller.
    """

    try:
        if dataset == "ohlcv" and payload_by_symbol:
            for symbol, symbol_data in payload_by_symbol.items():
                if "data" in symbol_data and symbol_data["data"]:
                    ohlcv_records = []
                    for row in symbol_data["data"]:
                        date_val = row.get("Date") or row.get("Datetime")
                        if date_val:
                            ohlcv_records.append(
                                OHLCVData(
                                    ticker=symbol,
                                    date=pd.to_datetime(date_val).to_pydatetime(),
                                    open=float(row.get("Open", 0)),
                                    high=float(row.get("High", 0)),
                                    low=float(row.get("Low", 0)),
                                    close=float(row.get("Close", 0)),
                                    volume=int(row.get("Volume", 0)),
                                    adjusted_close=(
                                        float(row.get("Adj Close", 0))
                                        if "Adj Close" in row
                                        else None
                                    ),
                                )
                            )
                    if ohlcv_records:
                        resources.sql_db.save_ohlcv(ohlcv_records)
                        resources.sql_db.update_cache_index(
                            symbol,
                            "ohlcv",
                            extra_info={
                                "row_count": len(ohlcv_records),
                                "latest_date": (
                                    ohlcv_records[-1].date.isoformat()
                                    if ohlcv_records
                                    else None
                                ),
                            },
                        )

        elif dataset == "fundamentals" and payload_by_symbol:
            for symbol, symbol_data in payload_by_symbol.items():
                if "error" not in symbol_data:
                    resources.sql_db.upsert_fundamentals(symbol_data)
                    resources.sql_db.update_cache_index(
                        symbol,
                        "fundamentals",
                        extra_info={"fundamentals_payload": symbol_data},
                    )

        elif dataset == "macro" and payload:
            if isinstance(payload, dict) and "error" not in payload:
                resources.sql_db.upsert_macro_indicators(payload)
                resources.sql_db.update_cache_index(
                    "MACRO", "macro", extra_info={"macro_payload": payload}
                )

        elif dataset == "news" and isinstance(payload, list) and payload:
            chunks: list[Any] = []
            normalized_articles = dedupe_articles_by_url(
                [article for article in payload if isinstance(article, dict)]
            )
            for article in normalized_articles:
                title = article.get("title", "")
                summary = article.get("summary", "")
                content = article.get("content", "")
                text_content = f"{title}\n{summary}\n{content}".strip()

                metadata = build_news_chunk_metadata(article, ticker)
                if text_content:
                    chunks.extend(
                        resources.vector_db.chunk_and_upsert(text_content, metadata)
                    )

            if ticker and normalized_articles:
                resources.sql_db.update_cache_index(
                    ticker,
                    "news",
                    extra_info=build_news_cache_summary(
                        normalized_articles,
                        chunk_count=len(chunks),
                        planned_intent_types=planned_news_intent_types or tuple(),
                        freshness_threshold=float(news_freshness_threshold or 0.0),
                    ),
                )

        return {"ok": True, "error": None}

    except Exception as exc:  # noqa: BLE001
        logger.error("Error storing data for %s: %s", dataset, exc, exc_info=True)
        return {"ok": False, "error": str(exc)}
