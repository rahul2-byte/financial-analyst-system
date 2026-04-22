"""Shared utility functions for agents."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

FUNDAMENTAL_CORE_FIELDS = [
    "marketCap",
    "currentPrice",
    "peRatio",
    "forwardPE",
    "priceToBook",
    "returnOnEquity",
    "profitMargins",
    "revenueGrowth",
    "earningsGrowth",
]

FUNDAMENTAL_CONTEXT_FIELDS = [
    "ticker",
    "name",
    "industry",
    "sector",
]

FUNDAMENTAL_ENRICHMENT_FIELDS = [
    "pegRatio",
    "debtToEquity",
    "dividendYield",
    "targetMeanPrice",
    "fiftyTwoWeekHigh",
    "fiftyTwoWeekLow",
]


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
        try:
            parsed = parsedate_to_datetime(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except (TypeError, ValueError, IndexError):
            return None
    return None


def _extract_timestamp(payload: Any) -> datetime | None:
    timestamps: list[datetime] = []

    if isinstance(payload, dict):
        for key in (
            "timestamp",
            "datetime",
            "date",
            "Date",
            "published",
            "published_date",
            "published_at",
            "fetched_at",
            "updated_at",
        ):
            if key in payload:
                parsed = _parse_datetime(payload.get(key))
                if parsed is not None:
                    timestamps.append(parsed)
        if "data" in payload and isinstance(payload["data"], list) and payload["data"]:
            parsed = _extract_timestamp(payload["data"][-1])
            if parsed is not None:
                timestamps.append(parsed)
        for value in payload.values():
            nested = _extract_timestamp(value)
            if nested is not None:
                timestamps.append(nested)
    if isinstance(payload, list):
        for item in payload:
            nested = _extract_timestamp(item)
            if nested is not None:
                timestamps.append(nested)
    return max(timestamps) if timestamps else None


def derive_freshness_score(payload: Any) -> float:
    """Score recency from the newest timestamp available in a payload.

    Expected semantics by payload shape:
    - OHLCV/news payloads: freshness comes from source timestamps in the payload.
    - Fundamentals/macro payloads without source timestamps: callers may attach
      fetch-time metadata such as ``fetched_at`` and freshness reflects that.
    - Payloads with no timestamp signal fall back to ``0.5`` to represent
      unknown recency rather than stale data.
    """
    timestamp = _extract_timestamp(payload)
    if timestamp is None:
        return 0.5

    now = datetime.now(UTC)
    age_seconds = max(0.0, (now - timestamp).total_seconds())
    age_days = age_seconds / 86400.0
    return max(0.0, min(1.0, 1.0 - (age_days / 30.0)))


def _freshness_from_window(payload: Any, stale_after_days: float) -> float:
    timestamp = _extract_timestamp(payload)
    if timestamp is None:
        return 0.5

    now = datetime.now(UTC)
    age_seconds = max(0.0, (now - timestamp).total_seconds())
    age_days = age_seconds / 86400.0
    window_days = max(float(stale_after_days), 1.0)
    return max(0.0, min(1.0, 1.0 - (age_days / window_days)))


def derive_news_freshness_score(payload: Any, stale_after_days: float) -> float:
    return _freshness_from_window(payload, stale_after_days)


def derive_snapshot_freshness_score(payload: Any, stale_after_days: float) -> float:
    return _freshness_from_window(payload, stale_after_days)


def derive_coverage_score(payload: Any) -> float:
    if payload is None:
        return 0.0
    if (
        isinstance(payload, dict)
        and "data" in payload
        and isinstance(payload["data"], list)
    ):
        return min(1.0, len(payload["data"]) / 200.0) if payload["data"] else 0.0
    if isinstance(payload, list):
        return min(1.0, len(payload) / 50.0) if payload else 0.0
    if isinstance(payload, dict):
        return min(1.0, len(payload.keys()) / 12.0) if payload else 0.0
    return 0.2


def derive_news_coverage_score(payload: Any, minimum_items: int) -> float:
    if not isinstance(payload, list) or not payload:
        return 0.0
    required = max(int(minimum_items), 1)
    return min(1.0, len(payload) / float(required))


def derive_required_fields_coverage(payload: Any, required_fields: list[str]) -> float:
    if not isinstance(payload, dict) or not required_fields:
        return 0.0
    present = 0
    for field in required_fields:
        if field in payload and payload[field] is not None:
            present += 1
    return min(1.0, present / float(len(required_fields)))


def derive_fundamental_schema_coverage(payload: Any) -> float:
    if not isinstance(payload, dict):
        return 0.0

    core = derive_required_fields_coverage(payload, FUNDAMENTAL_CORE_FIELDS)
    context = derive_required_fields_coverage(payload, FUNDAMENTAL_CONTEXT_FIELDS)
    enrichment = derive_required_fields_coverage(payload, FUNDAMENTAL_ENRICHMENT_FIELDS)

    return round((core * 0.7) + (context * 0.2) + (enrichment * 0.1), 4)


def extract_goal_symbols(goal: dict[str, Any]) -> list[str]:
    """Extract the *single* primary symbol for this research run.

    The current research pipeline is single-ticker. Even if the goal contains
    multiple instruments (e.g., a comparison query), downstream orchestration
    should operate on one primary symbol.

    Priority order (legacy-compatible intent):
    1. `goal['ticker']` (explicit primary)
    2. `goal['primary_instrument']['trading_symbol']`
    3. First `trading_symbol` found in `goal['instruments']`

    Returns:
    - `[SYMBOL]` when a primary symbol can be determined
    - `[]` when no symbol is present
    """

    ticker = goal.get("ticker")
    if isinstance(ticker, str) and ticker.strip():
        return [ticker.strip().upper()]

    primary = goal.get("primary_instrument")
    if isinstance(primary, dict):
        primary_symbol = primary.get("trading_symbol")
        if isinstance(primary_symbol, str) and primary_symbol.strip():
            return [primary_symbol.strip().upper()]

    instruments = goal.get("instruments", [])
    if isinstance(instruments, list):
        for instrument in instruments:
            if not isinstance(instrument, dict):
                continue
            symbol = instrument.get("trading_symbol")
            if isinstance(symbol, str) and symbol.strip():
                return [symbol.strip().upper()]

    return []


def _derive_required_dimensions(hypotheses: list[dict[str, Any]]) -> list[str]:
    """Derive required research dimensions from hypotheses."""
    dimensions = []
    for hypothesis in hypotheses:
        statement = str(hypothesis.get("statement", "")).lower()
        if "fundamental" in statement or "earnings" in statement:
            dimensions.extend(["profitability", "valuation", "balance_sheet"])
        if "macro" in statement:
            dimensions.append("macro_regime")
        if "sentiment" in statement or "news" in statement:
            dimensions.append("qualitative_sentiment")
    return sorted(set(dimensions))


DEFAULT_TASK_TEMPLATES: list[dict[str, str]] = [
    {
        "task_id": "fundamental_analysis",
        "agent": "fundamental_analysis",
        "priority": "P0",
    },
    {
        "task_id": "technical_analysis",
        "agent": "technical_analysis",
        "priority": "P1",
    },
    {
        "task_id": "sentiment_analysis",
        "agent": "sentiment_analysis",
        "priority": "P1",
    },
    {
        "task_id": "macro_analysis",
        "agent": "macro_analysis",
        "priority": "P1",
    },
    {
        "task_id": "contrarian_analysis",
        "agent": "contrarian_analysis",
        "priority": "P2",
    },
]


def selected_agents(state: dict[str, Any]) -> list[str]:
    approved = state.get("approved_agents", [])
    if not isinstance(approved, list) or not approved:
        return [template["agent"] for template in DEFAULT_TASK_TEMPLATES]
    selected: list[str] = []
    allowed = {template["agent"] for template in DEFAULT_TASK_TEMPLATES}
    for agent in approved:
        if isinstance(agent, str) and agent in allowed and agent not in selected:
            selected.append(agent)
    return selected or [template["agent"] for template in DEFAULT_TASK_TEMPLATES]


def task_sort_key(task: dict[str, Any]) -> tuple[int, str]:
    priority_map = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    return (
        priority_map.get(task.get("priority", "P3"), 3),
        str(task.get("task_id", "")),
    )
