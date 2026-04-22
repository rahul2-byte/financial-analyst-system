from __future__ import annotations

from typing import Any


def _shorten_text(value: str, limit: int = 240) -> str:
    text = value.replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def summarize_node_state(state: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "goal_present": isinstance(state.get("goal"), dict) and bool(state.get("goal")),
        "iteration_count": int(state.get("iteration_count", 0) or 0),
        "router_decision": state.get("router_decision"),
        "critic_decision": state.get("critic_decision"),
        "force_replan": bool(state.get("force_replan", False)),
        "validation_passed": bool(state.get("validation_passed", False)),
        "evaluation_passed": bool(state.get("evaluation_passed", False)),
        "evidence_strength": float(state.get("evidence_strength", 0.0) or 0.0),
        "confidence_score": float(state.get("confidence_score", 0.0) or 0.0),
    }

    tasks = state.get("tasks")
    if isinstance(tasks, list):
        summary["tasks_count"] = len(tasks)

    contexts = state.get("task_contexts")
    if isinstance(contexts, dict):
        summary["task_contexts_count"] = len(contexts)

    results = state.get("results")
    if isinstance(results, dict):
        summary["results_keys"] = list(results.keys())[:10]

    data_status = state.get("data_status")
    if isinstance(data_status, dict):
        summary["data_status_keys"] = list(data_status.keys())[:10]

    fetched_data = state.get("fetched_data")
    if isinstance(fetched_data, dict):
        summary["fetched_data_keys"] = list(fetched_data.keys())[:10]

    retries = state.get("retry_count_by_domain")
    if isinstance(retries, dict):
        summary["retry_count_by_domain"] = {
            str(key): int(value) if isinstance(value, int) else value
            for key, value in list(retries.items())[:10]
        }

    return summary


def _extract_symbols(state: dict[str, Any]) -> list[str]:
    goal = state.get("goal")
    if not isinstance(goal, dict):
        return []

    symbols: list[str] = []
    ticker = goal.get("ticker")
    if isinstance(ticker, str):
        symbols.append(ticker)

    instruments = goal.get("instruments")
    if not isinstance(instruments, list):
        return symbols

    for instrument in instruments:
        if not isinstance(instrument, dict):
            continue
        trading_symbol = instrument.get("trading_symbol")
        if isinstance(trading_symbol, str) and trading_symbol not in symbols:
            symbols.append(trading_symbol)

    return symbols


def summarize_node_output(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}

    for key in ("status", "reasoning", "next_action"):
        value = payload.get(key)
        if value is not None:
            if key == "reasoning" and isinstance(value, str):
                summary[key] = _shorten_text(value)
            else:
                summary[key] = value

    errors = payload.get("errors")
    if errors is not None:
        summary["errors"] = _normalize_errors(errors)

    collection_keys = {
        "tasks": "task_count",
        "task_contexts": "task_context_count",
        "results": "result_count",
        "data_plan": "data_plan_count",
    }

    for key, count_key in collection_keys.items():
        value = payload.get(key)
        if isinstance(value, list):
            summary[key] = value[:5]
            summary[count_key] = len(value)
        elif isinstance(value, dict):
            summary[key] = dict(list(value.items())[:5])
            summary[count_key] = len(value)

    if isinstance(payload.get("data"), dict):
        data = payload["data"]
        summary["data_keys"] = list(data.keys())[:10]

    retry_counts = payload.get("retry_count_by_domain")
    if isinstance(retry_counts, dict):
        summary["retry_count_by_domain"] = {
            str(key): int(value) if isinstance(value, int) else value
            for key, value in list(retry_counts.items())[:10]
        }

    if "final_output" in payload:
        final_output = payload.get("final_output")
        summary["final_output_type"] = type(final_output).__name__
        if isinstance(final_output, dict):
            summary["final_output_status"] = final_output.get("status")
            summary["final_output_decision"] = final_output.get("decision")

    return summary


def _normalize_errors(errors: Any) -> list[Any]:
    if errors is None:
        return []
    if isinstance(errors, list):
        return errors
    return [errors]


def build_node_audit_entry(
    node_name: str, state: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    symbols = _extract_symbols(state)

    return {
        "node": node_name,
        "ticker": symbols[0] if symbols else None,
        "symbols": symbols,
        "timeframe": state.get("timeframe"),
        "iteration_count": state.get("iteration_count"),
        "router_decision": state.get("router_decision"),
        "status": payload.get("status"),
        "reasoning": payload.get("reasoning"),
        "next_action": payload.get("next_action"),
        "output_summary": summarize_node_output(payload),
        "errors": _normalize_errors(payload.get("errors")),
    }
