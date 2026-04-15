"""Data fetcher node."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
import pandas as pd
import logging

from app.core.contracts.graph_node import finalize_node_output
from app.core.node_resources import resources
from app.config import settings
from data.schemas.market import OHLCVData
from data.news_pipeline.models import CompanyContext, NewsPipelineRecord
from data.news_pipeline.query_templates import QueryTemplateLibrary
from data.news_pipeline.runner import NewsPipelineRunner
from agents.shared.utils import (
    derive_fundamental_schema_coverage,
    derive_news_coverage_score,
    derive_news_freshness_score,
    derive_required_fields_coverage,
    derive_snapshot_freshness_score,
    extract_goal_symbols,
)

logger = logging.getLogger(__name__)
NEWS_FRESHNESS_THRESHOLD = 0.6
PLANNED_NEWS_INTENT_TYPES = tuple(QueryTemplateLibrary.keys())


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None

    candidate = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(candidate):
        return None
    return candidate.to_pydatetime()


def _resolve_source_domain(article: dict[str, Any]) -> str:
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


def _article_dedupe_key(article: dict[str, Any]) -> str:
    for key in (
        "dedupe_key",
        "article_hash",
        "canonical_url",
        "resolved_url",
        "original_url",
        "url",
        "link",
        "title",
    ):
        value = article.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _is_trusted_article(article: dict[str, Any]) -> bool:
    explicit_value = article.get("is_trusted_domain")
    if isinstance(explicit_value, bool):
        return explicit_value
    source_tier = article.get("source_tier")
    if isinstance(source_tier, int):
        return source_tier <= 2
    return False


def _is_open_web_article(article: dict[str, Any]) -> bool:
    source_type = article.get("source_type")
    if isinstance(source_type, str) and source_type.strip():
        return source_type.strip().lower() != "filing"
    return bool(article.get("url") or article.get("link"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _build_news_cache_summary(
    payload: list[dict[str, Any]], chunk_count: int
) -> dict[str, Any]:
    dedupe_keys = {
        dedupe_key
        for article in payload
        if (dedupe_key := _article_dedupe_key(article))
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
    latest_published_at = max(
        (
            published_at
            for published_at in (
                _parse_timestamp(
                    article.get("published_date") or article.get("published")
                )
                for article in payload
            )
            if published_at is not None
        ),
        default=None,
    )
    latest_fetch_at = max(
        (
            fetched_at
            for fetched_at in (
                _parse_timestamp(article.get("fetched_at")) for article in payload
            )
            if fetched_at is not None
        ),
        default=None,
    )

    coverage_by_intent: dict[str, dict[str, int]] = {}
    for intent_type in covered_intent_types:
        intent_articles = [
            article
            for article in payload
            if str(article.get("intent_type", "")).strip() == intent_type
        ]
        intent_dedupe_keys = {
            dedupe_key
            for article in intent_articles
            if (dedupe_key := _article_dedupe_key(article))
        }
        coverage_by_intent[intent_type] = {
            "article_count": len(intent_articles),
            "deduped_article_count": len(intent_dedupe_keys),
            "trusted_article_count": sum(
                1 for article in intent_articles if _is_trusted_article(article)
            ),
            "open_web_article_count": sum(
                1 for article in intent_articles if _is_open_web_article(article)
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
            1 for article in payload if _is_trusted_article(article)
        ),
        "open_web_article_count": sum(
            1 for article in payload if _is_open_web_article(article)
        ),
        "covered_intent_types": covered_intent_types,
        "missing_intent_types": [
            intent
            for intent in PLANNED_NEWS_INTENT_TYPES
            if intent not in covered_intent_types
        ],
        "query_variants": query_variants,
        "coverage_by_intent": coverage_by_intent,
        "timeframe": timeframe,
        "fresh_enough": freshness_score >= NEWS_FRESHNESS_THRESHOLD,
        "vector_ready": chunk_count > 0,
        "chunk_count": chunk_count,
    }


def _build_news_chunk_metadata(
    article: dict[str, Any], ticker: str | None
) -> dict[str, Any]:
    title = str(article.get("title", ""))
    content = str(article.get("content", ""))
    title_hash = str(article.get("title_hash") or _sha256(title))
    content_hash = str(article.get("content_hash") or _sha256(content))
    article_hash = str(
        article.get("article_hash") or _sha256(f"{title_hash}:{content_hash}")
    )
    dedupe_key = str(
        article.get("dedupe_key")
        or article.get("canonical_url")
        or article.get("url")
        or article_hash
    )
    metadata = {
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


def _stamp_news_fetched_at(payload: Any, fetched_at: str) -> Any:
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


def _store_data(
    dataset: str,
    payload: Any,
    ticker: str | None,
    payload_by_symbol: dict[str, Any] | None = None,
) -> None:
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
            chunks = []
            normalized_articles: list[dict[str, Any]] = []
            for article in payload:
                if not isinstance(article, dict):
                    continue
                normalized_articles.append(article)
                title = article.get("title", "")
                summary = article.get("summary", "")
                content = article.get("content", "")
                text_content = f"{title}\n{summary}\n{content}".strip()

                metadata = _build_news_chunk_metadata(article, ticker)
                if text_content:
                    chunks.extend(resources.vector_db.chunk_and_upsert(text_content, metadata))
            if ticker and normalized_articles:
                resources.sql_db.update_cache_index(
                    ticker,
                    "news",
                    extra_info=_build_news_cache_summary(
                        normalized_articles,
                        chunk_count=len(chunks),
                    ),
                )

    except Exception as e:
        logger.error(f"Error storing data for {dataset}: {e}", exc_info=True)


def _freshness_payload(dataset: str, payload: Any, fetched_at: str) -> Any:
    # Some providers expose no source-side as-of timestamp. In those cases we
    # record fetch-time recency explicitly so freshness is deterministic.
    if dataset in {"fundamentals", "macro"}:
        return {"payload": payload, "fetched_at": fetched_at}
    return payload


def _normalize_news_payload(payload: Any) -> Any:
    if not isinstance(payload, list):
        return payload

    normalized: list[Any] = []
    for item in payload:
        if isinstance(item, dict):
            normalized_item = dict(item)
            # Ensure both 'url' and 'link' exist
            url = (
                normalized_item.get("url")
                or normalized_item.get("link")
                or normalized_item.get("canonical_url")
                or ""
            )
            normalized_item["url"] = str(url)
            normalized_item["link"] = str(url)

            # Map published dates
            published_date = (
                normalized_item.get("published_date")
                or normalized_item.get("published")
                or normalized_item.get("date")
                or ""
            )
            normalized_item["published_date"] = str(published_date)

            # Map content
            content = (
                normalized_item.get("content")
                or normalized_item.get("body")
                or normalized_item.get("summary")
                or ""
            )
            normalized_item["content"] = str(content)

            normalized.append(normalized_item)
            continue
        model_dump = getattr(item, "model_dump", None)
        if callable(model_dump):
            normalized_item = model_dump(mode="json")
            if isinstance(normalized_item, dict):
                # Ensure both 'url' and 'link' exist
                url = (
                    normalized_item.get("url")
                    or normalized_item.get("link")
                    or normalized_item.get("canonical_url")
                    or ""
                )
                normalized_item["url"] = str(url)
                normalized_item["link"] = str(url)

                # Map published dates
                published_date = (
                    normalized_item.get("published_date")
                    or normalized_item.get("published")
                    or normalized_item.get("date")
                    or ""
                )
                normalized_item["published_date"] = str(published_date)

                # Map content
                content = (
                    normalized_item.get("content")
                    or normalized_item.get("body")
                    or normalized_item.get("summary")
                    or ""
                )
                normalized_item["content"] = str(content)

            normalized.append(normalized_item)
            continue
        normalized.append(item)
    return normalized


def _ohlcv_coverage(payload: Any, requirements: dict[str, Any]) -> float:
    if not isinstance(payload, dict):
        return 0.0
    data = payload.get("data", [])
    if not isinstance(data, list) or not data:
        return 0.0
    expected_points = max(1, int(requirements.get("expected_points", 1)))
    return min(1.0, len(data) / float(expected_points))


def _fundamentals_coverage(payload: Any, requirements: dict[str, Any]) -> float:
    del requirements
    return derive_fundamental_schema_coverage(payload)


def _macro_coverage(payload: Any, requirements: dict[str, Any]) -> float:
    return derive_required_fields_coverage(
        payload, list(requirements.get("required_fields", []))
    )


def _resolve_company_name(goal: dict[str, Any]) -> str | None:
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


def _extract_company_context(
    goal: dict[str, Any], ticker: str | None, company_name: str | None
) -> CompanyContext:
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


def _record_to_article(
    record: NewsPipelineRecord, timeframe: str | None
) -> dict[str, Any]:
    article = {
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
    return article


def _build_news_pipeline_runner() -> NewsPipelineRunner:
    return NewsPipelineRunner(
        max_articles_per_company=int(settings.MAX_ARTICLES_PER_COMPANY),
        min_quality_score=float(settings.MIN_QUALITY_SCORE),
        pipeline_version=str(settings.PIPELINE_VERSION),
    )


async def _fetch_planned_news(
    *,
    objective: str,
    ticker: str | None,
    company_name: str | None,
    timeframe: str | None,
    conversation_history: list[dict[str, Any]] | None,
    goal: dict[str, Any] | None = None,
) -> list[Any]:
    fetched_at = datetime.now(UTC).isoformat()
    del objective, conversation_history

    company_context = _extract_company_context(goal or {}, ticker, company_name)
    runner = _build_news_pipeline_runner()
    records = await runner.run(
        company=company_context,
        time_window_days=(
            30
            if not timeframe
            else 7 if str(timeframe).lower() in {"w", "1w", "7d"} else 30
        ),
    )
    payload = [_record_to_article(record, timeframe) for record in records]
    return _stamp_news_fetched_at(payload, fetched_at)


async def data_fetch_node(state: dict[str, Any]) -> dict[str, Any]:
    current_status = dict(state.get("data_status", {}))
    fetched_data = dict(state.get("fetched_data", {}))
    data_plan = state.get("data_plan", [])
    retries = dict(state.get("retry_count_by_domain", {}))
    retries["data_fetch"] = retries.get("data_fetch", 0) + 1

    goal = dict(state.get("goal", {}))
    symbols = extract_goal_symbols(goal)
    ticker = symbols[0] if symbols else goal.get("ticker")
    query = state.get("user_query", "")
    timeframe_policy = dict(state.get("timeframe_policy", {}))

    for item in data_plan:
        dataset = item.get("dataset")
        if not dataset:
            continue
        requirements = {
            **dict(timeframe_policy.get(dataset, {})),
            **dict(item.get("requirements", {})),
        }

        dataset_state = dict(current_status.get(dataset, {}))
        available = False
        coverage = float(dataset_state.get("coverage", 0.0))
        freshness = float(dataset_state.get("freshness", 0.0))
        error: str | None = None
        fetched: Any = None
        source = "fetch_attempt"
        dataset_payload = fetched_data.get(dataset)

        try:
            if dataset in {"ohlcv", "fundamentals"} and symbols:
                by_symbol: dict[str, dict[str, Any]] = {}
                payload_by_symbol: dict[str, Any] = {}
                for symbol in symbols:
                    fetched_at = datetime.now(UTC).isoformat()
                    if dataset == "ohlcv":
                        period = str(requirements.get("period", "1mo"))
                        interval = str(requirements.get("interval", "1d"))
                        symbol_data = resources.yf_fetcher.fetch_stock_price(
                            symbol, period=period, interval=interval
                        )
                    else:
                        symbol_data = resources.yf_fetcher.fetch_company_fundamentals(
                            symbol
                        )
                    symbol_available = bool(symbol_data)
                    symbol_coverage = (
                        _ohlcv_coverage(symbol_data, requirements)
                        if dataset == "ohlcv"
                        else _fundamentals_coverage(symbol_data, requirements)
                    )
                    symbol_freshness = derive_snapshot_freshness_score(
                        _freshness_payload(dataset, symbol_data, fetched_at),
                        stale_after_days=float(
                            requirements.get("stale_after_days", 90)
                        ),
                    )
                    by_symbol[symbol] = {
                        "available": symbol_available,
                        "coverage": symbol_coverage,
                        "freshness": symbol_freshness,
                        "source": "fetch_attempt",
                        "error": None if symbol_available else "INSUFFICIENT_DATA",
                    }
                    payload_by_symbol[symbol] = symbol_data

                dataset_state["by_symbol"] = by_symbol
                dataset_payload = {"by_symbol": payload_by_symbol}
                fetched = dataset_payload
                available = bool(by_symbol) and all(
                    detail.get("available", False) for detail in by_symbol.values()
                )
                coverage = min(
                    [
                        float(detail.get("coverage", 0.0))
                        for detail in by_symbol.values()
                    ]
                    or [0.0]
                )
                freshness = min(
                    [
                        float(detail.get("freshness", 0.0))
                        for detail in by_symbol.values()
                    ]
                    or [0.0]
                )
            elif dataset == "news":
                goal_objective = str(goal.get("objective", "")).strip()
                objective = (
                    goal_objective
                    or query
                    or (", ".join(symbols) if symbols else (ticker or ""))
                )
                fetched = await _fetch_planned_news(
                    objective=objective,
                    ticker=ticker,
                    company_name=_resolve_company_name(goal),
                    timeframe=state.get("timeframe"),
                    conversation_history=state.get("conversation_history"),
                    goal=goal,
                )
                available = bool(fetched)
                dataset_payload = fetched
                if available:
                    freshness = derive_news_freshness_score(
                        fetched,
                        stale_after_days=float(requirements.get("stale_after_days", 2)),
                    )
                    coverage = derive_news_coverage_score(
                        fetched,
                        minimum_items=int(requirements.get("minimum_items", 10)),
                    )
            elif dataset == "macro":
                fetched = resources.yf_fetcher.fetch_macro_indicators()
                available = bool(fetched)
                dataset_payload = fetched
        except Exception as fetch_error:  # noqa: BLE001
            error = str(fetch_error)

        if available and fetched is not None:
            fetched_at = datetime.now(UTC).isoformat()
            if dataset == "news":
                coverage = derive_news_coverage_score(
                    fetched,
                    minimum_items=int(requirements.get("minimum_items", 10)),
                )
                freshness = derive_news_freshness_score(
                    fetched,
                    stale_after_days=float(requirements.get("stale_after_days", 2)),
                )
            elif dataset == "macro":
                coverage = _macro_coverage(fetched, requirements)
                freshness = derive_snapshot_freshness_score(
                    _freshness_payload(dataset, fetched, fetched_at),
                    stale_after_days=float(requirements.get("stale_after_days", 7)),
                )

            # Persist data to the structured DB and vector DB
            _store_data(
                dataset=dataset,
                payload=fetched,
                ticker=ticker,
                payload_by_symbol=(
                    dataset_payload.get("by_symbol")
                    if isinstance(dataset_payload, dict)
                    else None
                ),
            )

        dataset_state["available"] = available
        dataset_state.setdefault("partial", True)
        dataset_state["source"] = source
        dataset_state["coverage"] = coverage
        dataset_state["freshness"] = freshness
        dataset_state["error"] = (
            error if error else (None if available else "INSUFFICIENT_DATA")
        )
        current_status[dataset] = dataset_state
        fetched_data[dataset] = dataset_payload

    payload = {
        "data_status": current_status,
        "fetched_data": fetched_data,
        "retry_count_by_domain": retries,
        "status": "partial",
        "reasoning": "Recorded deterministic fetch attempts and updated dataset statuses.",
        "confidence_score": 0.5,
        "next_action": "run_data_check",
        "data": {"data_status": current_status, "fetched_data": fetched_data},
        "errors": [],
    }
    return finalize_node_output("data_fetch_node", payload)
