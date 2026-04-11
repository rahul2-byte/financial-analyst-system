"""Data checker node."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.contracts.graph_node import finalize_node_output
from app.core.node_resources import resources
from app.core.orchestration_schemas import OfflineStatus
from app.core.prompts import prompt_manager
from app.core.tools.tool_system import ToolNamespace, tool_executor, tool_registry
from app.config.constants import MODEL_REASONING
from app.models.request_models import Message
from agents.shared.utils import (
    derive_freshness_score,
    derive_required_fields_coverage,
    derive_snapshot_freshness_score,
    extract_goal_symbols,
)

REQUIRED_DATASETS = ("ohlcv", "news", "fundamentals", "macro")
FRESHNESS_THRESHOLD = 0.6
MAX_OFFLINE_AUDIT_STEPS = 5

logger = logging.getLogger(__name__)


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


def _normalize_offline_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if "metadata" in normalized and "extra_info" not in normalized:
        normalized["extra_info"] = normalized.get("metadata")
    normalized.setdefault("extra_info", {})
    return normalized


def _merge_local_audit_status(
    data_status: dict[str, Any],
    symbol: str,
    offline: OfflineStatus,
    timeframe_policy: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(data_status)
    extra = dict(offline.extra_info or {})

    ohlcv_state = dict(merged.get("ohlcv", {}))
    by_symbol_ohlcv = dict(ohlcv_state.get("by_symbol", {}))
    by_symbol_ohlcv[symbol] = {
        "available": bool(offline.data_available),
        "source": "db_check",
        "error": None if offline.data_available else "LOCAL_DATA_MISSING",
    }
    if extra.get("latest_date"):
        freshness = derive_freshness_score({"date": extra.get("latest_date")})
        by_symbol_ohlcv[symbol]["freshness"] = freshness
    if extra.get("row_count") is not None:
        expected_points = float(
            timeframe_policy.get("ohlcv", {}).get("expected_points", 252)
        )
        by_symbol_ohlcv[symbol]["coverage"] = min(
            1.0, float(extra.get("row_count", 0)) / max(expected_points, 1.0)
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

    fundamentals_state = dict(merged.get("fundamentals", {}))
    by_symbol_fundamentals = dict(fundamentals_state.get("by_symbol", {}))
    fundamentals_requirements = dict(timeframe_policy.get("fundamentals", {}))
    fundamentals_payload = dict(extra.get("fundamentals_payload", {}))
    fundamentals_freshness = (
        derive_snapshot_freshness_score(
            fundamentals_payload,
            stale_after_days=float(fundamentals_requirements.get("stale_after_days", 90)),
        )
        if fundamentals_payload
        else 0.5
    )
    fundamentals_coverage = derive_required_fields_coverage(
        fundamentals_payload,
        list(fundamentals_requirements.get("required_fields", [])),
    )
    by_symbol_fundamentals[symbol] = {
        "available": bool(offline.data_available),
        "source": "db_check",
        "error": None if offline.data_available else "LOCAL_DATA_MISSING",
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

    # Handle News dataset with rich metadata
    news_state = dict(merged.get("news", {}))
    news_extra = dict(extra.get("news", {}))
    if news_extra:
        covered_intents = list(news_extra.get("covered_intent_types", []))
        news_coverage = len(covered_intents) / 5.0  # Assuming 5 required intent types
        news_fresh_enough = bool(news_extra.get("fresh_enough", False))
        news_vector_ready = bool(news_extra.get("vector_ready", False))

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

    # Handle Macro dataset (currently minimal)
    macro_state = dict(merged.get("macro", {}))
    macro_state.setdefault("available", False)
    macro_state.setdefault("source", "cache_index")
    macro_state.setdefault("freshness", 0.0)
    macro_state.setdefault("coverage", 0.0)
    macro_state.setdefault("error", "LOCAL_STATUS_UNKNOWN")
    merged["macro"] = macro_state

    return merged


async def _run_local_offline_audit(
    ticker: str,
) -> tuple[OfflineStatus | None, list[str]]:
    errors: list[str] = []
    llm_service = resources.llm_service
    model = MODEL_REASONING
    prompt = prompt_manager.get_prompt("market_offline.autonomous_audit", ticker=ticker)

    messages: list[Message] = [
        Message(
            role="system", content=prompt_manager.get_prompt("market_offline.system")
        ),
        Message(role="user", content=prompt),
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tool_registry.get_tools_by_namespace(ToolNamespace.MARKET)
    ]

    final_status: OfflineStatus | None = None
    for _ in range(MAX_OFFLINE_AUDIT_STEPS):
        response = await llm_service.generate_message(
            messages=messages, model=model, tools=tools
        )
        messages.append(response)
        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            func = tool_call.get("function", {})
            short_name = func.get("name")
            args = json.loads(func.get("arguments", "{}"))
            full_name = f"{ToolNamespace.MARKET.value}:{short_name}"
            tool_result = await tool_executor.execute(full_name, args)

            if not tool_result.success:
                errors.append(f"{full_name}: {tool_result.error}")
                result_content = json.dumps(
                    {"error": tool_result.error}, ensure_ascii=True
                )
            else:
                result_content = json.dumps(
                    tool_result.data, ensure_ascii=True, default=str
                )
                if short_name == "submit_offline_status":
                    try:
                        normalized = _normalize_offline_status_payload(
                            tool_result.data
                            if isinstance(tool_result.data, dict)
                            else {}
                        )
                        final_status = OfflineStatus.model_validate(normalized)
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"submit_offline_status invalid: {exc}")

            messages.append(
                Message(
                    role="tool",
                    content=result_content,
                    name=short_name,
                    tool_call_id=tool_call.get("id"),
                )
            )

        if final_status is not None:
            break

    if final_status is None:
        errors.append("offline audit unresolved")
    return final_status, errors


async def data_check_node(state: dict[str, Any]) -> dict[str, Any]:
    data_status = dict(state.get("data_status", {}))
    audit_errors: list[str] = []
    local_audit: dict[str, Any] = {}
    goal = dict(state.get("goal", {}))
    original_ticker = goal.get("ticker")
    timeframe_policy = dict(state.get("timeframe_policy", {}))

    goal_symbols = extract_goal_symbols(goal)

    if goal_symbols and _is_data_status_incomplete(data_status):
        resolved_symbols: list[str] = []
        try:
            reports: list[dict[str, Any]] = []
            for symbol in goal_symbols:
                offline, symbol_errors = await _run_local_offline_audit(symbol)
                audit_errors.extend(symbol_errors)
                if offline is None:
                    continue
                resolved_symbol = (offline.ticker_used or symbol).upper()
                resolved_symbols.append(resolved_symbol)
                data_status = _merge_local_audit_status(
                    data_status, resolved_symbol, offline, timeframe_policy
                )
                reports.append(
                    {
                        "input_symbol": symbol,
                        "resolved_symbol": resolved_symbol,
                        "data_available": offline.data_available,
                        "reasoning": offline.reasoning,
                        "extra_info": offline.extra_info,
                    }
                )
            if resolved_symbols:
                goal["ticker"] = resolved_symbols[0]
                goal["ticker_resolution_source"] = "offline_audit"
            local_audit = {
                "original_ticker": original_ticker,
                "resolved_ticker": goal.get("ticker"),
                "symbols_checked": goal_symbols,
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
    return finalize_node_output("data_check_node", payload)
