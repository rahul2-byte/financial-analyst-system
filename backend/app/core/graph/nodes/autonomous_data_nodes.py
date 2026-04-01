from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.node_resources import resources


REQUIRED_DATASETS = ("ohlcv", "news", "fundamentals", "macro")
FRESHNESS_THRESHOLD = 0.6


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (ValueError, OSError):
            return None
    if isinstance(value, str):
        for candidate in (value, value.replace("Z", "+00:00")):
            try:
                parsed = datetime.fromisoformat(candidate)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except ValueError:
                continue
    return None


def _extract_timestamp(payload: Any) -> datetime | None:
    if isinstance(payload, dict):
        for key in ("timestamp", "datetime", "date", "published", "published_at"):
            if key in payload:
                parsed = _parse_datetime(payload.get(key))
                if parsed is not None:
                    return parsed
        for value in payload.values():
            nested = _extract_timestamp(value)
            if nested is not None:
                return nested
    if isinstance(payload, list):
        for item in payload:
            nested = _extract_timestamp(item)
            if nested is not None:
                return nested
    return None


def _derive_freshness_score(payload: Any) -> float:
    timestamp = _extract_timestamp(payload)
    if timestamp is None:
        return 0.5

    now = datetime.now(UTC)
    age_seconds = max(0.0, (now - timestamp).total_seconds())
    age_days = age_seconds / 86400.0
    return max(0.0, min(1.0, 1.0 - (age_days / 30.0)))


def _derive_coverage_score(payload: Any) -> float:
    if payload is None:
        return 0.0
    if isinstance(payload, list):
        return min(1.0, len(payload) / 50.0) if payload else 0.0
    if isinstance(payload, dict):
        return min(1.0, len(payload.keys()) / 12.0) if payload else 0.0
    return 0.2


async def autonomous_data_checker_node(state: dict[str, Any]) -> dict[str, Any]:
    data_status = dict(state.get("data_status", {}))
    missing: list[str] = []
    stale: list[str] = []

    for dataset in REQUIRED_DATASETS:
        status = data_status.get(dataset, {})
        if not status.get("available", False):
            missing.append(dataset)
            continue
        if float(status.get("freshness", 0.0)) < FRESHNESS_THRESHOLD:
            stale.append(dataset)

    node_status = "success" if not missing and not stale else "partial"
    return {
        "data_check": {
            "missing_datasets": missing,
            "stale_datasets": stale,
        },
        "status": node_status,
        "reasoning": "Checked required datasets for availability and freshness.",
        "confidence_score": 0.8 if node_status == "success" else 0.55,
        "next_action": "run_research_plan" if node_status == "success" else "run_data_plan",
        "data": {
            "missing_datasets": missing,
            "stale_datasets": stale,
            "data_status": data_status,
        },
        "errors": [],
    }


async def autonomous_data_planner_node(state: dict[str, Any]) -> dict[str, Any]:
    checker = state.get("data_check", {})
    missing = checker.get("missing_datasets", [])
    stale = checker.get("stale_datasets", [])

    data_plan: list[dict[str, Any]] = []
    for dataset in missing:
        data_plan.append({"dataset": dataset, "priority": "P0", "action": "fetch"})
    for dataset in stale:
        data_plan.append({"dataset": dataset, "priority": "P1", "action": "refresh"})

    return {
        "data_plan": data_plan,
        "status": "success",
        "reasoning": "Prioritized data operations: missing first, stale second.",
        "confidence_score": 0.7,
        "next_action": "run_data_fetch",
        "data": {"data_plan": data_plan},
        "errors": [],
    }


async def autonomous_data_fetch_node(state: dict[str, Any]) -> dict[str, Any]:
    current_status = dict(state.get("data_status", {}))
    data_plan = state.get("data_plan", [])
    retries = dict(state.get("retry_count_by_domain", {}))
    retries["data_fetch"] = retries.get("data_fetch", 0) + 1

    ticker = state.get("goal", {}).get("ticker")
    query = state.get("user_query", "")

    for item in data_plan:
        dataset = item.get("dataset")
        if not dataset:
            continue

        dataset_state = dict(current_status.get(dataset, {}))
        available = False
        coverage = float(dataset_state.get("coverage", 0.0))
        freshness = float(dataset_state.get("freshness", 0.0))
        error: str | None = None
        fetched: Any = None

        try:
            if dataset in {"ohlcv", "fundamentals"} and ticker:
                if dataset == "ohlcv":
                    fetched = resources.yf_fetcher.fetch_stock_price(ticker)
                else:
                    fetched = resources.yf_fetcher.fetch_company_fundamentals(ticker)
                available = bool(fetched)
            elif dataset == "news":
                fetched = resources.rss_fetcher.fetch_market_news(query or (ticker or ""))
                available = bool(fetched)
            elif dataset == "macro":
                fetched = resources.yf_fetcher.fetch_macro_indicators()
                available = bool(fetched)
        except Exception as fetch_error:  # noqa: BLE001
            error = str(fetch_error)

        if available:
            coverage = _derive_coverage_score(fetched)
            freshness = _derive_freshness_score(fetched)

        dataset_state["available"] = available
        dataset_state.setdefault("partial", True)
        dataset_state["source"] = "fetch_attempt"
        dataset_state["coverage"] = coverage
        dataset_state["freshness"] = freshness
        dataset_state["error"] = error if error else (None if available else "INSUFFICIENT_DATA")
        current_status[dataset] = dataset_state

    return {
        "data_status": current_status,
        "retry_count_by_domain": retries,
        "status": "partial",
        "reasoning": "Recorded deterministic fetch attempts and updated dataset statuses.",
        "confidence_score": 0.5,
        "next_action": "run_data_check",
        "data": {"data_status": current_status},
        "errors": [],
    }
