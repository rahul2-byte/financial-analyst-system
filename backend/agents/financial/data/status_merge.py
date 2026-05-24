from __future__ import annotations

from typing import Any

from agents.shared.utils import (
    derive_freshness_score,
    derive_fundamental_schema_coverage,
    derive_snapshot_freshness_score,
)
from app.core.orchestration_schemas import OfflineStatus


def _aggregate_symbol_state(by_symbol: dict[str, Any]) -> tuple[bool, float, float]:
    available_values = [bool(entry.get("available", False)) for entry in by_symbol.values()]
    freshness_values = [float(entry.get("freshness", 0.5)) for entry in by_symbol.values()]
    coverage_values = [float(entry.get("coverage", 0.0)) for entry in by_symbol.values()]
    available = bool(available_values) and all(available_values)
    freshness = min(freshness_values) if freshness_values else 0.0
    coverage = min(coverage_values) if coverage_values else 0.0
    return available, freshness, coverage


def _merge_ohlcv_status(
    merged_status: dict[str, Any],
    *,
    symbol: str,
    offline_status: OfflineStatus,
    timeframe_policy: dict[str, Any],
) -> None:
    ohlcv_state = dict(merged_status.get("ohlcv", {}))
    by_symbol_ohlcv = dict(ohlcv_state.get("by_symbol", {}))

    ohlcv_evidence = offline_status.ohlcv_data or {}
    has_ohlcv_data = bool(ohlcv_evidence.get("has_data", False)) or bool(
        ohlcv_evidence.get("row_count", 0)
    )

    by_symbol_ohlcv[symbol] = {
        "available": has_ohlcv_data,
        "source": "db_check",
        "error": (
            None if has_ohlcv_data else str(ohlcv_evidence.get("error") or "LOCAL_DATA_MISSING")
        ),
    }
    if ohlcv_evidence.get("latest_date"):
        by_symbol_ohlcv[symbol]["freshness"] = derive_freshness_score(
            {"date": ohlcv_evidence.get("latest_date")}
        )
    if ohlcv_evidence.get("row_count") is not None:
        expected_points = float(timeframe_policy.get("ohlcv", {}).get("expected_points", 252))
        by_symbol_ohlcv[symbol]["coverage"] = min(
            1.0,
            float(ohlcv_evidence.get("row_count", 0)) / max(expected_points, 1.0),
        )

    ohlcv_state["by_symbol"] = by_symbol_ohlcv
    available, freshness, coverage = _aggregate_symbol_state(by_symbol_ohlcv)
    ohlcv_state["available"] = available
    ohlcv_state["freshness"] = freshness
    ohlcv_state["coverage"] = coverage
    ohlcv_state["source"] = "db_check"
    ohlcv_state["error"] = None if available else "LOCAL_DATA_MISSING"
    merged_status["ohlcv"] = ohlcv_state


def _merge_fundamentals_status(
    merged_status: dict[str, Any],
    *,
    symbol: str,
    offline_status: OfflineStatus,
    timeframe_policy: dict[str, Any],
) -> None:
    fundamentals_state = dict(merged_status.get("fundamentals", {}))
    by_symbol_fundamentals = dict(fundamentals_state.get("by_symbol", {}))
    fundamentals_requirements = dict(timeframe_policy.get("fundamentals", {}))

    fundamentals_payload = offline_status.fundamentals_data or {}
    has_fundamentals_data = bool(fundamentals_payload and fundamentals_payload.get("has_data"))
    fundamentals_freshness = (
        derive_snapshot_freshness_score(
            fundamentals_payload,
            stale_after_days=float(fundamentals_requirements.get("stale_after_days", 90)),
        )
        if has_fundamentals_data
        else 0.5
    )
    fundamentals_coverage = derive_fundamental_schema_coverage(fundamentals_payload)

    by_symbol_fundamentals[symbol] = {
        "available": has_fundamentals_data,
        "source": "db_check",
        "error": (
            None
            if has_fundamentals_data
            else str(fundamentals_payload.get("error") or "LOCAL_DATA_MISSING")
        ),
        "freshness": fundamentals_freshness,
        "coverage": fundamentals_coverage,
    }

    fundamentals_state["by_symbol"] = by_symbol_fundamentals
    available, freshness, coverage = _aggregate_symbol_state(by_symbol_fundamentals)
    fundamentals_state["available"] = available
    fundamentals_state["source"] = "db_check"
    fundamentals_state["error"] = None if available else "LOCAL_DATA_MISSING"
    fundamentals_state["freshness"] = freshness
    fundamentals_state["coverage"] = coverage
    merged_status["fundamentals"] = fundamentals_state


def _merge_news_status(
    merged_status: dict[str, Any],
    *,
    offline_status: OfflineStatus,
) -> None:
    news_state = dict(merged_status.get("news", {}))
    news_evidence = offline_status.news_data or {}
    if news_evidence:
        if "sql_cache" in news_evidence or "vector_db" in news_evidence:
            has_data = bool(news_evidence.get("has_data", False))
            sql_cache = news_evidence.get("sql_cache", {})
            latest_date = sql_cache.get("latest_date")
            news_state.update(
                {
                    "available": has_data,
                    "source": "db_check",
                    "freshness": (
                        derive_freshness_score({"date": latest_date}) if latest_date else 0.5
                    ),
                    "coverage": 1.0 if has_data else 0.0,
                    "error": (
                        None if has_data else str(news_evidence.get("error") or "LOCAL_DATA_MISSING")
                    ),
                }
            )
        else:
            covered_intents = list(news_evidence.get("covered_intent_types", []))
            news_fresh_enough = bool(news_evidence.get("fresh_enough", False))
            news_vector_ready = bool(news_evidence.get("vector_ready", False))
            is_available = news_fresh_enough and news_vector_ready
            error_code = None
            if not news_fresh_enough:
                error_code = "NEWS_STALE"
            elif not news_vector_ready:
                error_code = "NEWS_VECTOR_NOT_READY"
            news_state.update(
                {
                    "available": is_available,
                    "source": "cache_index",
                    "freshness": 1.0 if news_fresh_enough else 0.0,
                    "coverage": len(covered_intents) / 5.0,
                    "error": error_code,
                }
            )
    else:
        news_state.setdefault("available", False)
        news_state.setdefault("source", "cache_index")
        news_state.setdefault("freshness", 0.0)
        news_state.setdefault("coverage", 0.0)
        news_state.setdefault("error", "LOCAL_STATUS_UNKNOWN")
    merged_status["news"] = news_state


def _merge_macro_status(
    merged_status: dict[str, Any],
    *,
    offline_status: OfflineStatus,
) -> None:
    macro_state = dict(merged_status.get("macro", {}))
    macro_evidence = offline_status.macro_data or {}
    if macro_evidence:
        has_data = bool(macro_evidence.get("has_data", False))
        macro_state.update(
            {
                "available": has_data,
                "source": "db_check",
                "freshness": (
                    derive_freshness_score({"date": macro_evidence.get("latest_date")})
                    if macro_evidence.get("latest_date")
                    else 0.5
                ),
                "coverage": 1.0 if has_data else 0.0,
                "error": (
                    None if has_data else str(macro_evidence.get("error") or "LOCAL_DATA_MISSING")
                ),
            }
        )
    else:
        macro_state.setdefault("available", False)
        macro_state.setdefault("source", "cache_index")
        macro_state.setdefault("freshness", 0.0)
        macro_state.setdefault("coverage", 0.0)
        macro_state.setdefault("error", "LOCAL_STATUS_UNKNOWN")
    merged_status["macro"] = macro_state


def merge_local_audit_status(
    data_status: dict[str, Any],
    symbol: str,
    offline_status: OfflineStatus,
    timeframe_policy: dict[str, Any],
) -> dict[str, Any]:
    merged_status = dict(data_status)
    _merge_ohlcv_status(
        merged_status,
        symbol=symbol,
        offline_status=offline_status,
        timeframe_policy=timeframe_policy,
    )
    _merge_fundamentals_status(
        merged_status,
        symbol=symbol,
        offline_status=offline_status,
        timeframe_policy=timeframe_policy,
    )
    _merge_news_status(merged_status, offline_status=offline_status)
    _merge_macro_status(merged_status, offline_status=offline_status)
    return merged_status
