"""Financial data check node (graph runtime).

This node evaluates local availability for required datasets and updates
`state['goal']['ticker']` when a deterministic local symbol resolution succeeds.

Outputs (stable contract):
- `data_status`: per-dataset availability/freshness/coverage with error codes.
- `data_check.missing_datasets` / `data_check.stale_datasets`
- `next_action`: either `run_data_plan` (when missing/stale) or `run_research_plan`.

Implementation note:
The node uses `resources.sql_db` and `resources.vector_db` for offline evidence
and merges that evidence into a normalized `data_status` structure.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.audit import build_node_audit_entry
from app.core.contracts.graph_node import finalize_node_output
from app.core.node_resources import resources
from app.core.orchestration_schemas import OfflineStatus
from agents.financial.data.policy import (
    DATA_CHECK_FRESHNESS_THRESHOLD as FRESHNESS_THRESHOLD,
    REQUIRED_DATASETS,
)
from agents.shared.utils import (
    derive_freshness_score,
    derive_fundamental_schema_coverage,
    derive_snapshot_freshness_score,
    extract_goal_symbols,
)

logger = logging.getLogger(__name__)


def _build_data_check_audit(
    state: dict[str, Any],
    payload: dict[str, Any],
    goal: dict[str, Any],
    missing: list[str],
    stale: list[str],
    local_audit: dict[str, Any],
    data_status: dict[str, Any],
) -> dict[str, Any]:
    context_state = dict(state)
    context_state["goal"] = goal
    audit = build_node_audit_entry("data_check_node", context_state, payload)
    audit["decision_summary"] = {
        "resolved_ticker": local_audit.get("resolved_ticker") or goal.get("ticker"),
        "missing_datasets": missing,
        "stale_datasets": stale,
        "next_action": payload.get("next_action"),
        "dataset_statuses": [
            {
                "dataset": dataset,
                "available": bool(status.get("available", False)),
                "coverage": float(status.get("coverage", 0.0)),
                "freshness": float(status.get("freshness", 0.0)),
                "error": status.get("error"),
            }
            for dataset, status in data_status.items()
            if isinstance(status, dict)
        ],
    }
    return audit


def _is_data_status_incomplete(data_status: dict[str, Any]) -> bool:
    if not data_status:
        return True
    for dataset in REQUIRED_DATASETS:
        value = data_status.get(dataset)
        if not isinstance(value, dict):
            return True
        if "available" not in value:
            return True
    return False


def _empty_dataset_evidence(ticker: str | None = None) -> dict[str, Any]:
    evidence: dict[str, Any] = {"has_data": False}
    if ticker:
        evidence["ticker"] = ticker
    return evidence


def _missing_dataset_evidence(
    reason: str,
    ticker: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    evidence = _empty_dataset_evidence(ticker)
    evidence["error"] = reason
    evidence.update(extra)
    return evidence


def _news_info_for_ticker(ticker: str) -> dict[str, Any]:
    sql_raw = resources.sql_db.get_news_cache_info(ticker)
    vector_raw = resources.vector_db.get_news_info(ticker)

    # Defensive normalization: storage adapters should return dicts, but the node
    # must not crash if adapters evolve.
    sql_info = sql_raw if isinstance(sql_raw, dict) else {}
    vector_info = vector_raw if isinstance(vector_raw, dict) else {}

    has_sql_cache = bool(sql_info.get("has_data", False))
    vector_ready = sql_info.get("vector_ready")
    has_vector_news = bool(vector_info.get("has_news", False))

    error = None
    has_data = has_vector_news
    if has_sql_cache and vector_ready is False:
        error = "NEWS_VECTOR_NOT_READY"
    elif has_sql_cache and not has_vector_news:
        error = "LOCAL_DATA_MISSING"
    elif not has_sql_cache:
        error = "LOCAL_DATA_MISSING"

    return {
        "ticker": ticker,
        "sql_cache": sql_info,
        "vector_db": vector_info,
        "has_data": has_data,
        "error": error,
    }


def _choose_ranked_symbol_match(
    requested_symbol: str,
    matches: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    if not matches:
        return None, "SYMBOL_NOT_FOUND_LOCALLY"

    top = matches[0]
    top_symbol = str(top.get("trading_symbol") or "").strip().upper()
    top_score = float(top.get("score", 0.0) or 0.0)
    if not top_symbol:
        return None, "SYMBOL_NOT_FOUND_LOCALLY"

    if len(matches) == 1:
        return top_symbol, None

    second = matches[1]
    second_symbol = str(second.get("trading_symbol") or "").strip().upper()
    second_score = float(second.get("score", 0.0) or 0.0)

    if top_symbol != second_symbol and abs(top_score - second_score) < 1e-9:
        return None, "SYMBOL_AMBIGUOUS"

    return top_symbol, None


def _resolve_local_symbol(requested_symbol: str) -> tuple[str | None, str | None]:
    candidate = str(requested_symbol or "").strip().upper()
    if not candidate:
        return None, "SYMBOL_NOT_FOUND_LOCALLY"

    exact = resources.sql_db.resolve_exact_symbol(candidate)
    if isinstance(exact, dict) and exact.get("trading_symbol"):
        return str(exact["trading_symbol"]).upper(), None

    alias = resources.sql_db.resolve_alias(candidate)
    if isinstance(alias, dict) and alias.get("trading_symbol"):
        return str(alias["trading_symbol"]).upper(), None

    ranked = resources.sql_db.search_instruments_ranked(
        candidate,
        limit=5,
        segment="EQ",
    )
    if isinstance(ranked, list):
        return _choose_ranked_symbol_match(candidate, ranked)

    return None, "SYMBOL_NOT_FOUND_LOCALLY"


def _build_offline_status_from_tool_evidence(
    requested_symbol: str,
    submitted_args: dict[str, Any],
    tool_evidence: dict[str, Any],
) -> OfflineStatus:
    """Builds OfflineStatus from tool evidence, ignoring hallucinations in submitted_args."""

    # Extract evidence from tools
    ohlcv_ev = tool_evidence.get("get_ticker_info", {"has_data": False})
    fund_ev = tool_evidence.get("get_fundamentals_info", {"has_data": False})
    news_ev = tool_evidence.get("get_news_info", {"has_data": False})
    macro_ev = tool_evidence.get("get_macro_info", {"has_data": False})

    # Tool evidence always overrides submitted_args (anti-hallucination)
    data_available = (
        bool(ohlcv_ev.get("has_data"))
        and bool(fund_ev.get("has_data"))
        and bool(news_ev.get("has_data"))
        and bool(macro_ev.get("has_data"))
    )

    return OfflineStatus(
        data_available=data_available,
        ticker_used=submitted_args.get("ticker_used", requested_symbol.upper()),
        reasoning=submitted_args.get("reasoning", ""),
        ohlcv_data=ohlcv_ev,
        fundamentals_data=fund_ev,
        news_data=news_ev,
        macro_data=macro_ev,
    )


def _build_deterministic_offline_status(
    requested_symbol: str,
    resolved_symbol: str | None,
    resolution_error: str | None,
) -> OfflineStatus:
    macro_data = resources.sql_db.get_macro_info()

    if resolved_symbol is None:
        reason = resolution_error or "SYMBOL_NOT_FOUND_LOCALLY"
        reasoning = (
            f"Could not resolve {requested_symbol} uniquely from local instrument search"
            if reason == "SYMBOL_AMBIGUOUS"
            else f"Could not resolve {requested_symbol} from local instrument search"
        )
        return OfflineStatus(
            data_available=False,
            ticker_used=requested_symbol.upper(),
            reasoning=reasoning,
            ohlcv_data=_missing_dataset_evidence(reason, requested_symbol.upper()),
            fundamentals_data=_missing_dataset_evidence(
                reason, requested_symbol.upper()
            ),
            news_data=_missing_dataset_evidence(reason, requested_symbol.upper()),
            macro_data=(
                macro_data
                if isinstance(macro_data, dict) and macro_data.get("has_data")
                else _missing_dataset_evidence("LOCAL_DATA_MISSING")
            ),
        )

    ohlcv_data = resources.sql_db.get_ticker_info(resolved_symbol)
    if not ohlcv_data.get("has_data"):
        ohlcv_data = _missing_dataset_evidence(
            str(ohlcv_data.get("error") or "LOCAL_DATA_MISSING"),
            resolved_symbol,
            **ohlcv_data,
        )

    fundamentals_data = resources.sql_db.get_fundamentals_info(resolved_symbol)
    if not fundamentals_data.get("has_data"):
        fundamentals_data = _missing_dataset_evidence(
            str(fundamentals_data.get("error") or "LOCAL_DATA_MISSING"),
            resolved_symbol,
            **fundamentals_data,
        )

    news_data = _news_info_for_ticker(resolved_symbol)
    if not news_data.get("has_data"):
        news_data = {
            **news_data,
            "error": str(news_data.get("error") or "LOCAL_DATA_MISSING"),
        }

    if not isinstance(macro_data, dict) or not macro_data.get("has_data"):
        macro_data = _missing_dataset_evidence("LOCAL_DATA_MISSING")

    missing = []
    for dataset_name, payload in (
        ("ohlcv", ohlcv_data),
        ("fundamentals", fundamentals_data),
        ("news", news_data),
        ("macro", macro_data),
    ):
        if not bool(payload.get("has_data", False)):
            missing.append(dataset_name)

    reasoning = f"Resolved {requested_symbol.upper()} to {resolved_symbol} using local instrument search"
    if missing:
        reasoning = f"{reasoning}; missing datasets: {', '.join(missing)}"
    else:
        reasoning = f"{reasoning}; all required datasets available"

    return OfflineStatus(
        data_available=not missing,
        ticker_used=resolved_symbol,
        reasoning=reasoning,
        ohlcv_data=ohlcv_data,
        fundamentals_data=fundamentals_data,
        news_data=news_data,
        macro_data=macro_data,
    )


def _merge_ohlcv_status(
    merged: dict[str, Any],
    *,
    symbol: str,
    offline: OfflineStatus,
    timeframe_policy: dict[str, Any],
) -> None:
    """Merge OHLCV evidence into `merged['ohlcv']`.

    Pure update of the provided `merged` dict (legacy behavior).
    """

    ohlcv_state = dict(merged.get("ohlcv", {}))
    by_symbol_ohlcv = dict(ohlcv_state.get("by_symbol", {}))

    ohlcv_evidence = offline.ohlcv_data or {}
    has_ohlcv_data = bool(ohlcv_evidence.get("has_data", False)) or bool(
        ohlcv_evidence.get("row_count", 0)
    )

    by_symbol_ohlcv[symbol] = {
        "available": has_ohlcv_data,
        "source": "db_check",
        "error": (
            None
            if has_ohlcv_data
            else str(ohlcv_evidence.get("error") or "LOCAL_DATA_MISSING")
        ),
    }
    if ohlcv_evidence.get("latest_date"):
        freshness = derive_freshness_score({"date": ohlcv_evidence.get("latest_date")})
        by_symbol_ohlcv[symbol]["freshness"] = freshness
    if ohlcv_evidence.get("row_count") is not None:
        expected_points = float(
            timeframe_policy.get("ohlcv", {}).get("expected_points", 252)
        )
        by_symbol_ohlcv[symbol]["coverage"] = min(
            1.0, float(ohlcv_evidence.get("row_count", 0)) / max(expected_points, 1.0)
        )

    ohlcv_state["by_symbol"] = by_symbol_ohlcv
    available_values = [
        bool(entry.get("available", False)) for entry in by_symbol_ohlcv.values()
    ]
    ohlcv_state["available"] = bool(available_values) and all(available_values)
    freshness_values = [
        float(entry.get("freshness", 0.5)) for entry in by_symbol_ohlcv.values()
    ]
    coverage_values = [
        float(entry.get("coverage", 0.0)) for entry in by_symbol_ohlcv.values()
    ]
    ohlcv_state["freshness"] = min(freshness_values) if freshness_values else 0.0
    ohlcv_state["coverage"] = min(coverage_values) if coverage_values else 0.0
    ohlcv_state["source"] = "db_check"
    ohlcv_state["error"] = None if ohlcv_state["available"] else "LOCAL_DATA_MISSING"
    merged["ohlcv"] = ohlcv_state


def _merge_fundamentals_status(
    merged: dict[str, Any],
    *,
    symbol: str,
    offline: OfflineStatus,
    timeframe_policy: dict[str, Any],
) -> None:
    """Merge fundamentals evidence into `merged['fundamentals']`."""

    fundamentals_state = dict(merged.get("fundamentals", {}))
    by_symbol_fundamentals = dict(fundamentals_state.get("by_symbol", {}))
    fundamentals_requirements = dict(timeframe_policy.get("fundamentals", {}))

    fundamentals_payload = offline.fundamentals_data or {}
    fundamentals_freshness = (
        derive_snapshot_freshness_score(
            fundamentals_payload,
            stale_after_days=float(
                fundamentals_requirements.get("stale_after_days", 90)
            ),
        )
        if fundamentals_payload and fundamentals_payload.get("has_data")
        else 0.5
    )
    fundamentals_coverage = derive_fundamental_schema_coverage(fundamentals_payload)

    by_symbol_fundamentals[symbol] = {
        "available": bool(
            fundamentals_payload and fundamentals_payload.get("has_data")
        ),
        "source": "db_check",
        "error": (
            None
            if (fundamentals_payload and fundamentals_payload.get("has_data"))
            else str(fundamentals_payload.get("error") or "LOCAL_DATA_MISSING")
        ),
        "freshness": fundamentals_freshness,
        "coverage": fundamentals_coverage,
    }

    fundamentals_state["by_symbol"] = by_symbol_fundamentals
    fund_available_values = [
        bool(entry.get("available", False)) for entry in by_symbol_fundamentals.values()
    ]
    fundamentals_state["available"] = bool(fund_available_values) and all(
        fund_available_values
    )
    fundamentals_state["source"] = "db_check"
    fundamentals_state["error"] = (
        None if fundamentals_state["available"] else "LOCAL_DATA_MISSING"
    )
    fundamentals_state["freshness"] = min(
        [
            float(entry.get("freshness", 0.5))
            for entry in by_symbol_fundamentals.values()
        ]
        or [0.0]
    )
    fundamentals_state["coverage"] = min(
        [float(entry.get("coverage", 0.0)) for entry in by_symbol_fundamentals.values()]
        or [0.0]
    )
    merged["fundamentals"] = fundamentals_state


def _merge_news_status(
    merged: dict[str, Any],
    *,
    offline: OfflineStatus,
) -> None:
    """Merge news evidence into `merged['news']`.

    Supports the new structured `sql_cache/vector_db` evidence as well as older
    cache-index-style metadata.
    """

    news_state = dict(merged.get("news", {}))
    news_evidence = offline.news_data or {}
    if news_evidence:
        if "sql_cache" in news_evidence or "vector_db" in news_evidence:
            has_data = news_evidence.get("has_data", False)
            news_coverage = 1.0 if has_data else 0.0
            sql_cache = news_evidence.get("sql_cache", {})
            latest_date = sql_cache.get("latest_date")
            news_freshness = (
                derive_freshness_score({"date": latest_date}) if latest_date else 0.5
            )
            news_state.update(
                {
                    "available": has_data,
                    "source": "db_check",
                    "freshness": news_freshness,
                    "coverage": news_coverage,
                    "error": (
                        None
                        if has_data
                        else str(news_evidence.get("error") or "LOCAL_DATA_MISSING")
                    ),
                }
            )
        else:
            covered_intents = list(news_evidence.get("covered_intent_types", []))
            news_coverage = len(covered_intents) / 5.0
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
                    "coverage": news_coverage,
                    "error": error_code,
                }
            )
    else:
        news_state.setdefault("available", False)
        news_state.setdefault("source", "cache_index")
        news_state.setdefault("freshness", 0.0)
        news_state.setdefault("coverage", 0.0)
        news_state.setdefault("error", "LOCAL_STATUS_UNKNOWN")
    merged["news"] = news_state


def _merge_macro_status(
    merged: dict[str, Any],
    *,
    offline: OfflineStatus,
) -> None:
    """Merge macro evidence into `merged['macro']`."""

    macro_state = dict(merged.get("macro", {}))
    macro_evidence = offline.macro_data or {}
    if macro_evidence:
        has_data = macro_evidence.get("has_data", False)
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
                    None
                    if has_data
                    else str(macro_evidence.get("error") or "LOCAL_DATA_MISSING")
                ),
            }
        )
    else:
        macro_state.setdefault("available", False)
        macro_state.setdefault("source", "cache_index")
        macro_state.setdefault("freshness", 0.0)
        macro_state.setdefault("coverage", 0.0)
        macro_state.setdefault("error", "LOCAL_STATUS_UNKNOWN")
    merged["macro"] = macro_state


def _merge_local_audit_status(
    data_status: dict[str, Any],
    symbol: str,
    offline: OfflineStatus,
    timeframe_policy: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(data_status)

    _merge_ohlcv_status(
        merged, symbol=symbol, offline=offline, timeframe_policy=timeframe_policy
    )
    _merge_fundamentals_status(
        merged, symbol=symbol, offline=offline, timeframe_policy=timeframe_policy
    )
    _merge_news_status(merged, offline=offline)
    _merge_macro_status(merged, offline=offline)

    return merged


async def _run_local_offline_audit(
    ticker: str,
) -> tuple[OfflineStatus | None, list[str]]:
    normalized = str(ticker or "").strip().upper()
    resolved_symbol, resolution_error = _resolve_local_symbol(normalized)
    return (
        _build_deterministic_offline_status(
            normalized,
            resolved_symbol,
            resolution_error,
        ),
        [],
    )


async def data_check_node(state: dict[str, Any]) -> dict[str, Any]:
    data_status = dict(state.get("data_status", {}))
    audit_errors: list[str] = []
    local_audit: dict[str, Any] = {}
    goal = dict(state.get("goal", {}))
    original_ticker = goal.get("ticker")
    timeframe_policy = dict(state.get("timeframe_policy", {}))
    # `extract_goal_symbols()` returns a *single* primary symbol as a one-item
    # list (single-ticker pipeline).
    extracted = extract_goal_symbols(goal)
    primary_symbol = extracted[0] if extracted else None

    if (
        isinstance(primary_symbol, str)
        and primary_symbol
        and _is_data_status_incomplete(data_status)
    ):
        resolved_symbols: list[str] = []
        try:
            reports: list[dict[str, Any]] = []

            offline, symbol_errors = await _run_local_offline_audit(primary_symbol)
            audit_errors.extend(symbol_errors)
            if offline is not None:
                resolved_symbol = (offline.ticker_used or primary_symbol).upper()
                resolved_symbols.append(resolved_symbol)
                data_status = _merge_local_audit_status(
                    data_status, resolved_symbol, offline, timeframe_policy
                )
                reports.append(
                    {
                        "input_symbol": primary_symbol,
                        "resolved_symbol": resolved_symbol,
                        "data_available": offline.data_available,
                        "reasoning": offline.reasoning,
                        "extra_info": offline.model_dump(
                            include={
                                "ohlcv_data",
                                "fundamentals_data",
                                "news_data",
                                "macro_data",
                            }
                        ),
                    }
                )
            if resolved_symbols:
                goal["ticker"] = resolved_symbols[0]
                goal["ticker_resolution_source"] = "offline_audit"
            local_audit = {
                "original_ticker": original_ticker,
                "resolved_ticker": goal.get("ticker"),
                "symbols_checked": [primary_symbol],
                "reports": reports,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("autonomous offline audit failed: %s", exc, exc_info=True)
            audit_errors = [f"offline_audit_error: {exc}"]

    missing: list[str] = []
    stale: list[str] = []

    for dataset in REQUIRED_DATASETS:
        status = data_status.get(dataset, {})
        if not status.get("available", False):
            missing.append(dataset)
            continue
        if float(status.get("freshness", 0.0)) < FRESHNESS_THRESHOLD:
            stale.append(dataset)
            continue
        minimum_coverage = float(
            timeframe_policy.get(dataset, {}).get("minimum_coverage_ratio", 0.0)
        )
        if float(status.get("coverage", 0.0)) < minimum_coverage:
            stale.append(dataset)

    node_status = "success" if not missing and not stale else "partial"
    payload = {
        "goal": goal,
        "data_status": data_status,
        "data_check": {
            "missing_datasets": missing,
            "stale_datasets": stale,
            "local_audit": local_audit,
        },
        "status": node_status,
        "reasoning": "Checked required datasets for availability and freshness.",
        "confidence_score": 0.8 if node_status == "success" else 0.55,
        "next_action": (
            "run_research_plan" if node_status == "success" else "run_data_plan"
        ),
        "data": {
            "missing_datasets": missing,
            "stale_datasets": stale,
            "data_status": data_status,
            "local_audit": local_audit,
        },
        "errors": audit_errors,
    }
    payload["data"]["audit"] = _build_data_check_audit(
        state, payload, goal, missing, stale, local_audit, data_status
    )
    return finalize_node_output("data_check_node", payload)
