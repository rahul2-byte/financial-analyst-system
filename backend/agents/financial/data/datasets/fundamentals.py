"""Fundamentals dataset helpers.

Behavior-preserving extraction from `agents.financial.data.data_fetch_node`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agents.shared.utils import derive_snapshot_freshness_score
from app.core.node_resources import resources
from agents.shared.utils import derive_fundamental_schema_coverage


def load_fundamentals_from_sql(symbol: str) -> dict[str, Any] | None:
    """Load fundamentals from SQL and return the legacy payload shape."""

    payload = resources.sql_db.get_fundamentals_info(symbol)
    if not isinstance(payload, dict) or not bool(payload.get("has_data", False)):
        return None
    return dict(payload)


def fundamentals_coverage(payload: Any, requirements: dict[str, Any]) -> float:
    """Coverage heuristic for fundamentals payloads."""

    del requirements
    return derive_fundamental_schema_coverage(payload)


def materialize_fundamentals_by_symbol(
    symbols: list[str], dataset_state: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    by_symbol_state = dataset_state.get("by_symbol")
    by_symbol: dict[str, dict[str, Any]] = (
        dict(by_symbol_state) if isinstance(by_symbol_state, dict) else {}
    )
    payload_by_symbol: dict[str, Any] = {}

    for symbol in symbols:
        symbol_payload = load_fundamentals_from_sql(symbol)
        payload_by_symbol[symbol] = symbol_payload or {}

        symbol_status = by_symbol.get(symbol, {})
        if not isinstance(symbol_status, dict):
            symbol_status = {}

        symbol_available = bool(symbol_payload)
        by_symbol[symbol] = {
            "available": symbol_available,
            "coverage": float(
                symbol_status.get("coverage", dataset_state.get("coverage", 0.0))
            ),
            "freshness": float(
                symbol_status.get("freshness", dataset_state.get("freshness", 0.0))
            ),
            "source": "db_load",
            "error": None if symbol_available else "LOCAL_DATA_MISSING",
        }

    return by_symbol, payload_by_symbol


def fetch_fundamentals_by_symbol(
    symbols: list[str], requirements: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    by_symbol: dict[str, dict[str, Any]] = {}
    payload_by_symbol: dict[str, Any] = {}

    for symbol in symbols:
        fetched_at = datetime.now(UTC).isoformat()
        symbol_data = resources.yf_fetcher.fetch_company_fundamentals(symbol)
        symbol_available = bool(symbol_data)
        by_symbol[symbol] = {
            "available": symbol_available,
            "coverage": fundamentals_coverage(symbol_data, requirements),
            "freshness": derive_snapshot_freshness_score(
                {"payload": symbol_data, "fetched_at": fetched_at},
                stale_after_days=float(requirements.get("stale_after_days", 90)),
            ),
            "source": "fetch_attempt",
            "error": None if symbol_available else "INSUFFICIENT_DATA",
        }
        payload_by_symbol[symbol] = symbol_data

    return by_symbol, payload_by_symbol
