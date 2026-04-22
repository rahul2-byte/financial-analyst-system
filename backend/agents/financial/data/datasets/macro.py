"""Macro dataset helpers.

Behavior-preserving extraction from `agents.financial.data.data_fetch_node`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agents.shared.utils import derive_snapshot_freshness_score
from app.core.node_resources import resources
from agents.shared.utils import derive_required_fields_coverage


def load_macro_from_cache_index() -> dict[str, Any] | None:
    """Load macro payload from the SQL cache index (legacy storage location)."""

    status = resources.sql_db.get_cache_status("MACRO")
    if not isinstance(status, dict):
        return None
    extra = status.get("macro", {}).get("extra_info", {})
    payload = extra.get("macro_payload") if isinstance(extra, dict) else None
    return dict(payload) if isinstance(payload, dict) and payload else None


def macro_coverage(payload: Any, requirements: dict[str, Any]) -> float:
    """Coverage heuristic for macro payloads based on required field presence."""

    return derive_required_fields_coverage(
        payload, list(requirements.get("required_fields", []))
    )


def materialize_macro_dataset(
    requirements: dict[str, Any], dataset_state: dict[str, Any]
) -> dict[str, Any] | None:
    payload = load_macro_from_cache_index()
    if payload is None:
        return None
    return {
        "dataset_payload": payload,
        "fetched": payload,
        "available": True,
        "coverage": macro_coverage(payload, requirements),
        "freshness": float(dataset_state.get("freshness", 0.0)),
        "source": "db_load",
    }


def fetch_macro_dataset(requirements: dict[str, Any]) -> dict[str, Any]:
    payload = resources.yf_fetcher.fetch_macro_indicators()
    fetched_at = datetime.now(UTC).isoformat()
    return {
        "dataset_payload": payload,
        "fetched": payload,
        "available": bool(payload),
        "coverage": macro_coverage(payload, requirements),
        "freshness": derive_snapshot_freshness_score(
            {"payload": payload, "fetched_at": fetched_at},
            stale_after_days=float(requirements.get("stale_after_days", 7)),
        ),
        "source": "fetch_attempt",
    }
