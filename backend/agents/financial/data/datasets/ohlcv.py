"""OHLCV dataset helpers.

Behavior-preserving extraction from `agents.financial.data.data_fetch_node`.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from agents.shared.utils import derive_snapshot_freshness_score
from app.core.node_resources import resources


def ohlcv_start_date(end_date: datetime, period: str) -> datetime:
    """Compute a best-effort start date for a given OHLCV period.

    This is a heuristic mapping used for local materialization from SQL.
    """

    period_days = {
        "1mo": 35,
        "3mo": 110,
        "6mo": 220,
        "1y": 400,
        "3y": 1100,
        "5y": 1900,
        "10y": 3800,
        "ytd": 400,
    }
    return end_date - timedelta(days=int(period_days.get(period, 400)))


def load_ohlcv_from_sql(
    symbol: str, requirements: dict[str, Any]
) -> dict[str, Any] | None:
    """Load OHLCV rows for `symbol` from SQL and return the legacy payload shape.

    Returns a dict with keys:
    - `ticker`, `period`, `interval`, `data` (list of OHLCV rows)

    Returns None when no rows are available.
    """

    latest = resources.sql_db.get_latest_date(symbol)
    if latest is None:
        return None

    period = str(requirements.get("period", "1y"))
    interval = str(requirements.get("interval", "1d"))
    start = ohlcv_start_date(latest, period)

    rows = resources.sql_db.get_ohlcv(symbol, start_date=start, end_date=latest)
    if not rows:
        return None

    records: list[dict[str, Any]] = []
    for row in rows:
        date_value = getattr(row, "date", None)
        if date_value is None:
            continue
        records.append(
            {
                "Date": date_value.isoformat(),
                "Open": float(getattr(row, "open", 0.0)),
                "High": float(getattr(row, "high", 0.0)),
                "Low": float(getattr(row, "low", 0.0)),
                "Close": float(getattr(row, "close", 0.0)),
                "Volume": int(getattr(row, "volume", 0) or 0),
                "Adj Close": (
                    float(getattr(row, "adjusted_close", 0.0))
                    if getattr(row, "adjusted_close", None) is not None
                    else None
                ),
            }
        )

    if not records:
        return None

    return {"ticker": symbol, "period": period, "interval": interval, "data": records}


def ohlcv_coverage(payload: Any, requirements: dict[str, Any]) -> float:
    """Compute a simple coverage ratio for OHLCV payloads."""

    if not isinstance(payload, dict):
        return 0.0
    data = payload.get("data", [])
    if not isinstance(data, list) or not data:
        return 0.0
    expected_points = max(1, int(requirements.get("expected_points", 1)))
    return min(1.0, len(data) / float(expected_points))


def materialize_ohlcv_by_symbol(
    symbols: list[str],
    requirements: dict[str, Any],
    dataset_state: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    by_symbol_state = dataset_state.get("by_symbol")
    by_symbol: dict[str, dict[str, Any]] = (
        dict(by_symbol_state) if isinstance(by_symbol_state, dict) else {}
    )
    payload_by_symbol: dict[str, Any] = {}

    for symbol in symbols:
        symbol_payload = load_ohlcv_from_sql(symbol, requirements)
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


def fetch_ohlcv_by_symbol(
    symbols: list[str], requirements: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    by_symbol: dict[str, dict[str, Any]] = {}
    payload_by_symbol: dict[str, Any] = {}

    for symbol in symbols:
        period = str(requirements.get("period", "1mo"))
        interval = str(requirements.get("interval", "1d"))
        symbol_data = resources.yf_fetcher.fetch_stock_price(
            symbol, period=period, interval=interval
        )
        symbol_available = bool(symbol_data)
        by_symbol[symbol] = {
            "available": symbol_available,
            "coverage": ohlcv_coverage(symbol_data, requirements),
            "freshness": derive_snapshot_freshness_score(
                symbol_data,
                stale_after_days=float(requirements.get("stale_after_days", 90)),
            ),
            "source": "fetch_attempt",
            "error": None if symbol_available else "INSUFFICIENT_DATA",
        }
        payload_by_symbol[symbol] = symbol_data

    return by_symbol, payload_by_symbol
