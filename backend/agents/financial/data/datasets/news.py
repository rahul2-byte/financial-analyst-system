"""News dataset helpers.

This module contains the online news fetching path used by `data_fetch_node`.

Behavior-preserving extraction from legacy helpers in
`agents.financial.data.data_fetch_node`.

Key intent:
- Keep the `data_fetch_node` public surface stable while concentrating the news
  pipeline mechanics (company context extraction + record normalization) here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.config import settings
from agents.shared.utils import derive_news_coverage_score, derive_news_freshness_score
from agents.financial.data.news.vector_materialize import load_news_from_vector_db
from data.news_pipeline.models import CompanyContext, NewsPipelineRecord
from data.news_pipeline.runner import NewsPipelineRunner


def resolve_company_name(goal: dict[str, Any]) -> str | None:
    """Best-effort company name for news pipeline execution.

    Prefers explicit `goal['company_name']` / `goal['company']`, otherwise scans
    `goal['instruments']` for `company_name` or `name`.
    """

    company_name = goal.get("company_name") or goal.get("company")
    if isinstance(company_name, str) and company_name.strip():
        return company_name.strip()

    instruments = goal.get("instruments")
    if isinstance(instruments, list):
        for instrument in instruments:
            if not isinstance(instrument, dict):
                continue
            candidate = instrument.get("company_name") or instrument.get("name")
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()

    return None


def extract_company_context(
    goal: dict[str, Any],
    ticker: str | None,
    company_name: str | None,
) -> CompanyContext:
    """Convert goal + ticker hints into a `CompanyContext` for the news pipeline.

    This preserves legacy heuristics for NSE/BSE symbols and suffix handling.
    """

    nse_symbol: str | None = None
    bse_code: str | None = None
    sector: str | None = None

    instruments = goal.get("instruments")
    if isinstance(instruments, list):
        for instrument in instruments:
            if not isinstance(instrument, dict):
                continue
            nse_symbol = (
                nse_symbol
                or instrument.get("nse_symbol")
                or instrument.get("trading_symbol")
            )
            bse_code = (
                bse_code
                or instrument.get("bse_code")
                or instrument.get("bse_scrip_code")
            )
            sector = sector or instrument.get("sector")

    nse_symbol = nse_symbol or goal.get("nse_symbol")
    bse_code = bse_code or goal.get("bse_code")
    sector = sector or goal.get("sector")

    normalized_ticker = str(ticker or "").strip()
    if normalized_ticker.endswith(".NS"):
        nse_symbol = nse_symbol or normalized_ticker.removesuffix(".NS")
        normalized_ticker = normalized_ticker.removesuffix(".NS")
    elif normalized_ticker.endswith(".BO"):
        bse_code = bse_code or normalized_ticker.removesuffix(".BO")
        normalized_ticker = normalized_ticker.removesuffix(".BO")
    elif normalized_ticker.isdigit():
        bse_code = bse_code or normalized_ticker
    else:
        nse_symbol = nse_symbol or normalized_ticker

    return CompanyContext(
        ticker=normalized_ticker or str(ticker or "UNKNOWN"),
        company_name=company_name or normalized_ticker or "Unknown Company",
        nse_symbol=str(nse_symbol).strip() if nse_symbol else None,
        bse_code=str(bse_code).strip() if bse_code else None,
        sector=str(sector).strip() if sector else None,
    )


def record_to_article(
    record: NewsPipelineRecord, timeframe: str | None
) -> dict[str, Any]:
    """Normalize a `NewsPipelineRecord` into the legacy article dict shape."""

    return {
        "ticker": record.ticker,
        "company_name": record.company_name,
        "title": record.title,
        "summary": record.snippet,
        "content": record.article_text or record.snippet or "",
        "url": record.url,
        "link": record.url,
        "canonical_url": record.canonical_url,
        "published_date": (
            record.publish_time.isoformat() if record.publish_time else ""
        ),
        "source": record.source_domain,
        "source_domain": record.source_domain,
        "source_type": record.source_type,
        "source_tier": record.source_tier,
        "quality_score": record.quality_score,
        "paywall_detected": record.paywall_detected,
        "extraction_status": record.extraction_status,
        "relevance_check": record.relevance_check,
        "is_duplicate": record.is_duplicate,
        "cluster_id": record.cluster_id,
        "query_intent": record.query_intent,
        "intent_type": record.query_intent,
        "search_provider": record.search_provider,
        "query_variant": record.query_intent,
        "timeframe": str(timeframe or ""),
        "pipeline_version": record.pipeline_version,
        "is_trusted_domain": record.source_tier <= 2,
    }


def build_news_pipeline_runner() -> NewsPipelineRunner:
    """Construct a `NewsPipelineRunner` from settings (legacy)."""

    return NewsPipelineRunner(
        max_articles_per_company=int(settings.MAX_ARTICLES_PER_COMPANY),
        min_quality_score=float(settings.MIN_QUALITY_SCORE),
        pipeline_version=str(settings.PIPELINE_VERSION),
    )


def stamp_news_fetched_at(payload: Any, fetched_at: str) -> Any:
    """Ensure each article item has `fetched_at` set.

    Legacy behavior:
    - If payload is not a list, return it unchanged.
    - For list items that are dicts, setdefault('fetched_at', fetched_at).
    """

    if not isinstance(payload, list):
        return payload

    stamped_payload: list[Any] = []
    for item in payload:
        if not isinstance(item, dict):
            stamped_payload.append(item)
            continue
        stamped_item = dict(item)
        stamped_item.setdefault("fetched_at", fetched_at)
        stamped_payload.append(stamped_item)
    return stamped_payload


def build_news_objective(
    goal: dict[str, Any], query: str, symbols: list[str], ticker: str | None
) -> str:
    goal_objective = str(goal.get("objective", "")).strip()
    return (
        goal_objective or query or (", ".join(symbols) if symbols else (ticker or ""))
    )


def materialize_news_dataset(
    ticker: str | None, requirements: dict[str, Any]
) -> dict[str, Any] | None:
    if not isinstance(ticker, str) or not ticker.strip():
        return None

    minimum_items = int(requirements.get("minimum_items", 10))
    payload = load_news_from_vector_db(ticker.strip(), limit=max(minimum_items, 1000))
    if payload is None:
        return None

    return {
        "dataset_payload": payload,
        "fetched": payload,
        "available": True,
        "coverage": derive_news_coverage_score(payload, minimum_items=minimum_items),
        "freshness": derive_news_freshness_score(
            payload,
            stale_after_days=float(requirements.get("stale_after_days", 2)),
        ),
        "source": "vector_db_load",
    }


async def fetch_planned_news(
    *,
    objective: str,
    ticker: str | None,
    company_name: str | None,
    timeframe: str | None,
    conversation_history: list[dict[str, Any]] | None,
    goal: dict[str, Any] | None = None,
) -> list[Any]:
    """Fetch news via the news pipeline runner (online path).

    Behavior-preserving note:
    `objective` and `conversation_history` are accepted for interface stability
    but are not currently used by the legacy implementation.
    """

    fetched_at = datetime.now(UTC).isoformat()
    del objective, conversation_history

    company_context = extract_company_context(goal or {}, ticker, company_name)
    runner = build_news_pipeline_runner()
    records = await runner.run(
        company=company_context,
        time_window_days=(
            30
            if not timeframe
            else 7 if str(timeframe).lower() in {"w", "1w", "7d"} else 30
        ),
    )
    payload = [record_to_article(record, timeframe) for record in records]
    return stamp_news_fetched_at(payload, fetched_at)
