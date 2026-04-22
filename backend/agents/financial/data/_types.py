"""Internal types for the financial data nodes.

This package currently passes large, shape-shifting `dict[str, Any]` payloads between
graph nodes (data_check -> data_plan -> data_fetch). That is a stable *external*
contract we are preserving.

This module introduces small internal type hints (TypedDicts) so refactors can be
mechanical and safer without changing runtime payload shapes.
"""

from __future__ import annotations

from typing import Any, TypedDict


class DataPlanItem(TypedDict):
    """One planned operation for one dataset.

    Mirrors the runtime shape built by `data_plan_node` and consumed by
    `data_fetch_node`.
    """

    dataset: str
    priority: str
    action: str
    requirements: dict[str, Any]


class DatasetStatus(TypedDict, total=False):
    """Status snapshot for one dataset in `state['data_status']`.

    The nodes treat `available/coverage/freshness` as heuristics for whether a
    dataset can be used in downstream steps.

    Common keys used today:
    - `available`: True if the dataset is usable.
    - `coverage`: 0..1 completeness heuristic.
    - `freshness`: 0..1 recency heuristic.
    - `source`: provenance label (e.g. 'db_load', 'fetch_attempt').
    - `error`: error code/string when unavailable.
    - `partial`: legacy flag set by fetch node.
    - `by_symbol`: per-symbol detail dict for multi-symbol flows.
    """

    available: bool
    coverage: float
    freshness: float
    source: str
    error: str | None
    partial: bool
    by_symbol: dict[str, dict[str, Any]]
