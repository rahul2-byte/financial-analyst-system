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
from app.core.observability import observe, opik_context
from app.core.orchestration_schemas import OfflineStatus
from agents.financial.data.policy import (
    DATA_CHECK_FRESHNESS_THRESHOLD as FRESHNESS_THRESHOLD,
    REQUIRED_DATASETS,
)
from agents.financial.data.evidence_utils import (
    as_dict_or_empty,
    missing_dataset_evidence,
    normalize_dataset_evidence,
)
from agents.financial.data.status_merge import merge_local_audit_status
from agents.financial.data.symbol_resolution import canonicalize_ticker
from agents.shared.utils import (
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


def _news_info_for_ticker(ticker: str) -> dict[str, Any]:
    sql_raw = resources.sql_db.get_news_cache_info(ticker)
    vector_raw = resources.vector_db.get_news_info(ticker)

    # Defensive normalization: storage adapters should return dicts, but the node
    # must not crash if adapters evolve.
    sql_info = as_dict_or_empty(sql_raw)
    vector_info = as_dict_or_empty(vector_raw)

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
    candidate = canonicalize_ticker(requested_symbol)
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


def _build_deterministic_offline_status(
    requested_symbol: str,
    resolved_symbol: str | None,
    resolution_error: str | None,
) -> OfflineStatus:
    macro_payload = resources.sql_db.get_macro_info()

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
            ohlcv_data=missing_dataset_evidence(reason, requested_symbol.upper()),
            fundamentals_data=missing_dataset_evidence(
                reason, requested_symbol.upper()
            ),
            news_data=missing_dataset_evidence(reason, requested_symbol.upper()),
            macro_data=(
                macro_payload
                if isinstance(macro_payload, dict) and macro_payload.get("has_data")
                else missing_dataset_evidence("LOCAL_DATA_MISSING")
            ),
        )

    ohlcv_data = normalize_dataset_evidence(
        resources.sql_db.get_ticker_info(resolved_symbol),
        ticker=resolved_symbol,
    )

    fundamentals_data = normalize_dataset_evidence(
        resources.sql_db.get_fundamentals_info(resolved_symbol),
        ticker=resolved_symbol,
    )

    news_data = _news_info_for_ticker(resolved_symbol)
    if not news_data.get("has_data"):
        news_data = {
            **news_data,
            "error": str(news_data.get("error") or "LOCAL_DATA_MISSING"),
        }

    macro_data = normalize_dataset_evidence(macro_payload)

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


@observe(name="Data:Check", as_type="span")
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
                data_status = merge_local_audit_status(
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
            audit_errors.append(f"offline_audit_error: {exc}")

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

    opik_context.update_current_span(
        metadata={
            "missing_datasets": missing,
            "stale_datasets": stale,
            "node_status": node_status,
        }
    )

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
