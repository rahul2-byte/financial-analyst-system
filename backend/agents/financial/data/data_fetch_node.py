"""Financial data fetch node (graph runtime).

This node is part of the autonomous data pipeline:

1. `data_check_node` determines which datasets are missing/stale.
2. `data_plan_node` builds a prioritized list of dataset operations.
3. `data_fetch_node` executes that plan by:
   - materializing from local storage when possible
   - fetching from online providers when required
   - computing `coverage` and `freshness` heuristics
   - persisting payloads into SQL and/or the vector DB

Behavior contract (must remain stable):
- Reads `state['data_plan']`, `state['timeframe_policy']`, `state['data_status']`.
- Writes updated `data_status` and `fetched_data` into its output payload.
- Returns a contract-valid node payload via `finalize_node_output`.

Implementation note:
Most dataset-specific logic has been extracted into `agents.financial.data.*`
modules. This file keeps a few legacy helper functions as stable patch points for
unit tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict
import logging

from app.core.audit import build_node_audit_entry
from app.core.contracts.graph_node import finalize_node_output
from app.core.node_resources import resources  # noqa: F401 - legacy test patch point
from app.core.observability import observe, opik_context
from data.news_pipeline.query_templates import QueryTemplateLibrary
from agents.shared.utils import (
    derive_news_coverage_score,
    derive_news_freshness_score,
    extract_goal_symbols,
)

from agents.financial.data.policy import (
    DATA_FETCH_FRESHNESS_THRESHOLD,
    NEWS_FRESHNESS_THRESHOLD,
    REQUIRED_DATASETS,
)
from agents.financial.data.news.vector_materialize import load_news_from_vector_db
from agents.financial.data.news.metrics import (
    build_news_cache_summary as _build_news_cache_summary_impl,
)
from agents.financial.data.persistence import persist_dataset
from agents.financial.data.datasets.ohlcv import (
    fetch_ohlcv_by_symbol,
    load_ohlcv_from_sql,
    materialize_ohlcv_by_symbol,
    ohlcv_coverage,
)
from agents.financial.data.datasets.fundamentals import (
    fetch_fundamentals_by_symbol,
    fundamentals_coverage,
    load_fundamentals_from_sql,
    materialize_fundamentals_by_symbol,
)
from agents.financial.data.datasets.macro import (
    fetch_macro_dataset,
    load_macro_from_cache_index,
    macro_coverage,
    materialize_macro_dataset,
)
from agents.financial.data.datasets import news as news_dataset
from agents.financial.data.datasets.news import resolve_company_name

logger = logging.getLogger(__name__)
PLANNED_NEWS_INTENT_TYPES = tuple(QueryTemplateLibrary.keys())


class DatasetOperationContext(TypedDict):
    dataset: str
    action: str
    requirements: dict[str, Any]
    dataset_state: dict[str, Any]
    dataset_payload: Any
    symbols: list[str]
    ticker: str | None
    goal: dict[str, Any]
    query: str
    timeframe: Any
    conversation_history: list[dict[str, Any]] | None
    materialize_error: str | None


class DatasetOperationResult(TypedDict):
    dataset: str
    dataset_state: dict[str, Any]
    dataset_payload: Any
    fetched: Any
    available: bool
    coverage: float
    freshness: float
    source: str
    error: str | None
    performed_network_fetch: bool
    should_persist: bool


def _build_materialize_plan(timeframe_policy: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "dataset": dataset,
            "priority": "P0",
            "action": "materialize",
            "requirements": dict(timeframe_policy.get(dataset, {})),
        }
        for dataset in REQUIRED_DATASETS
    ]


def _dataset_ready_for_materialization(
    dataset: str,
    status: dict[str, Any],
    timeframe_policy: dict[str, Any],
) -> bool:
    if not status.get("available", False):
        return False
    if float(status.get("freshness", 0.0)) < DATA_FETCH_FRESHNESS_THRESHOLD:
        return False
    minimum_coverage = float(
        timeframe_policy.get(dataset, {}).get("minimum_coverage_ratio", 0.0)
    )
    return float(status.get("coverage", 0.0)) >= minimum_coverage


def _required_status_ready_for_materialization(
    data_status: dict[str, Any],
    timeframe_policy: dict[str, Any],
) -> bool:
    return all(
        _dataset_ready_for_materialization(
            dataset,
            dict(data_status.get(dataset, {})),
            timeframe_policy,
        )
        for dataset in REQUIRED_DATASETS
    )


def _required_payloads_materialized(fetched_data: dict[str, Any]) -> bool:
    def _has_by_symbol_payload(value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        by_symbol = value.get("by_symbol")
        return isinstance(by_symbol, dict) and any(bool(v) for v in by_symbol.values())

    if not _has_by_symbol_payload(fetched_data.get("ohlcv")):
        return False
    if not _has_by_symbol_payload(fetched_data.get("fundamentals")):
        return False
    if not isinstance(fetched_data.get("macro"), dict) or not fetched_data.get("macro"):
        return False
    news_value = fetched_data.get("news")
    return isinstance(news_value, list) and bool(news_value)


def _load_ohlcv_from_sql(
    symbol: str, requirements: dict[str, Any]
) -> dict[str, Any] | None:
    """Legacy wrapper (kept for minimal churn)."""

    return load_ohlcv_from_sql(symbol, requirements)


def _load_fundamentals_from_sql(symbol: str) -> dict[str, Any] | None:
    """Legacy wrapper (kept for minimal churn)."""

    return load_fundamentals_from_sql(symbol)


def _load_macro_from_cache_index() -> dict[str, Any] | None:
    """Legacy wrapper (kept for minimal churn)."""

    return load_macro_from_cache_index()


def _load_news_from_vector_db(
    ticker: str,
    *,
    limit: int,
) -> list[dict[str, Any]] | None:
    # Backwards-compatible shim: implementation now lives in
    # `agents.financial.data.news.vector_materialize`.
    return load_news_from_vector_db(ticker, limit=limit)


def _build_data_fetch_audit(
    state: dict[str, Any],
    payload: dict[str, Any],
    data_plan: list[dict[str, Any]],
    touched_data_status: dict[str, Any],
) -> dict[str, Any]:
    audit = build_node_audit_entry("data_fetch_node", state, payload)
    retries = state.get("retry_count_by_domain", {})
    audit["decision_summary"] = {
        "planned_datasets": [
            str(item.get("dataset", "")) for item in data_plan if item.get("dataset")
        ],
        "fetched_dataset_count": len(touched_data_status),
        "retry_count_by_domain": dict(retries) if isinstance(retries, dict) else {},
        "next_action": payload.get("next_action"),
        "dataset_outcomes": [
            {
                "dataset": dataset,
                "available": bool(status.get("available", False)),
                "error": status.get("error"),
            }
            for dataset, status in touched_data_status.items()
            if isinstance(status, dict)
        ],
        "dataset_outcomes_detailed": [
            {
                "dataset": dataset,
                "available": bool(status.get("available", False)),
                "error": status.get("error"),
                "source": status.get("source"),
                "freshness": status.get("freshness"),
                "coverage": status.get("coverage"),
                "partial": bool(status.get("partial", False)),
            }
            for dataset, status in touched_data_status.items()
            if isinstance(status, dict)
        ],
    }
    return audit


def _build_news_cache_summary(
    payload: list[dict[str, Any]],
    chunk_count: int,
) -> dict[str, Any]:
    """Legacy public helper used by tests.

    The implementation moved to `agents.financial.data.news.metrics`.
    """

    return _build_news_cache_summary_impl(
        payload,
        chunk_count=chunk_count,
        planned_intent_types=PLANNED_NEWS_INTENT_TYPES,
        freshness_threshold=NEWS_FRESHNESS_THRESHOLD,
    )


def _store_data(
    dataset: str,
    payload: Any,
    ticker: str | None,
    payload_by_symbol: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Backwards-compatible shim: persistence is now owned by
    # `agents.financial.data.persistence`.
    return persist_dataset(
        dataset=dataset,
        payload=payload,
        ticker=ticker,
        payload_by_symbol=payload_by_symbol,
        planned_news_intent_types=PLANNED_NEWS_INTENT_TYPES,
        news_freshness_threshold=NEWS_FRESHNESS_THRESHOLD,
    )


def _freshness_payload(dataset: str, payload: Any, fetched_at: str) -> Any:
    # Some providers expose no source-side as-of timestamp. In those cases we
    # record fetch-time recency explicitly so freshness is deterministic.
    if dataset in {"fundamentals", "macro"}:
        return {"payload": payload, "fetched_at": fetched_at}
    return payload


def _ohlcv_coverage(payload: Any, requirements: dict[str, Any]) -> float:
    """Legacy wrapper (kept for minimal churn)."""

    return ohlcv_coverage(payload, requirements)


def _fundamentals_coverage(payload: Any, requirements: dict[str, Any]) -> float:
    """Legacy wrapper (kept for minimal churn)."""

    return fundamentals_coverage(payload, requirements)


def _macro_coverage(payload: Any, requirements: dict[str, Any]) -> float:
    """Legacy wrapper (kept for minimal churn)."""

    return macro_coverage(payload, requirements)


async def _fetch_planned_news(
    *,
    objective: str,
    ticker: str | None,
    company_name: str | None,
    timeframe: str | None,
    conversation_history: list[dict[str, Any]] | None,
    goal: dict[str, Any] | None = None,
) -> list[Any]:
    # This helper is intentionally kept as a stable import/patch point for unit
    # tests. Implementation uses `datasets.news` for the heavy lifting.
    fetched_at = datetime.now(UTC).isoformat()
    del objective, conversation_history

    company_context = news_dataset.extract_company_context(
        goal or {}, ticker, company_name
    )
    runner = _build_news_pipeline_runner()
    records = await runner.run(
        company=company_context,
        time_window_days=(
            30
            if not timeframe
            else 7 if str(timeframe).lower() in {"w", "1w", "7d"} else 30
        ),
    )
    payload = [news_dataset.record_to_article(record, timeframe) for record in records]
    return news_dataset.stamp_news_fetched_at(payload, fetched_at)


def _build_news_pipeline_runner():
    """Legacy patch point for tests.

    The news pipeline runner construction now lives in `datasets.news`, but tests
    monkeypatch this symbol from `data_fetch_node`.
    """

    return news_dataset.build_news_pipeline_runner()


def build_operation_context(
    *,
    state: dict[str, Any],
    item: dict[str, Any],
    timeframe_policy: dict[str, Any],
    symbols: list[str],
    ticker: str | None,
    goal: dict[str, Any],
    query: str,
) -> DatasetOperationContext:
    dataset = str(item.get("dataset") or "")
    action = str(item.get("action") or "fetch").strip().lower()
    requirements = {
        **dict(timeframe_policy.get(dataset, {})),
        **dict(item.get("requirements", {})),
    }
    current_status = dict(state.get("data_status", {}))
    fetched_data = dict(state.get("fetched_data", {}))
    dataset_state = dict(current_status.get(dataset, {}))

    return {
        "dataset": dataset,
        "action": action,
        "requirements": requirements,
        "dataset_state": dataset_state,
        "dataset_payload": fetched_data.get(dataset),
        "symbols": list(symbols),
        "ticker": ticker,
        "goal": dict(goal),
        "query": query,
        "timeframe": state.get("timeframe"),
        "conversation_history": state.get("conversation_history"),
        "materialize_error": None,
    }


def _summarize_by_symbol(
    by_symbol: dict[str, dict[str, Any]],
) -> tuple[bool, float, float]:
    available = bool(by_symbol) and all(
        detail.get("available", False) for detail in by_symbol.values()
    )
    coverage = min(
        [float(detail.get("coverage", 0.0)) for detail in by_symbol.values()] or [0.0]
    )
    freshness = min(
        [float(detail.get("freshness", 0.0)) for detail in by_symbol.values()] or [0.0]
    )
    return available, coverage, freshness


def materialize_dataset(
    context: DatasetOperationContext,
) -> DatasetOperationResult | None:
    dataset = context["dataset"]
    requirements = context["requirements"]
    dataset_state = dict(context["dataset_state"])
    symbols = context["symbols"]
    ticker = context["ticker"]

    try:
        if dataset == "ohlcv" and symbols:
            by_symbol, payload_by_symbol = materialize_ohlcv_by_symbol(
                symbols, requirements, dataset_state
            )
            available, coverage, freshness = _summarize_by_symbol(by_symbol)
            if not available:
                return None
            dataset_state["by_symbol"] = by_symbol
            dataset_payload = {"by_symbol": payload_by_symbol}
            return {
                "dataset": dataset,
                "dataset_state": dataset_state,
                "dataset_payload": dataset_payload,
                "fetched": dataset_payload,
                "available": available,
                "coverage": coverage,
                "freshness": freshness,
                "source": "db_load",
                "error": None,
                "performed_network_fetch": False,
                "should_persist": False,
            }

        if dataset == "fundamentals" and symbols:
            by_symbol, payload_by_symbol = materialize_fundamentals_by_symbol(
                symbols, dataset_state
            )
            available, coverage, freshness = _summarize_by_symbol(by_symbol)
            if not available:
                return None
            dataset_state["by_symbol"] = by_symbol
            dataset_payload = {"by_symbol": payload_by_symbol}
            return {
                "dataset": dataset,
                "dataset_state": dataset_state,
                "dataset_payload": dataset_payload,
                "fetched": dataset_payload,
                "available": available,
                "coverage": coverage,
                "freshness": freshness,
                "source": "db_load",
                "error": None,
                "performed_network_fetch": False,
                "should_persist": False,
            }

        if dataset == "news" and isinstance(ticker, str) and ticker.strip():
            minimum_items = int(requirements.get("minimum_items", 10))
            cached = _load_news_from_vector_db(
                ticker.strip(), limit=max(minimum_items, 1000)
            )
            if cached is None:
                return None
            return {
                "dataset": dataset,
                "dataset_state": dataset_state,
                "dataset_payload": cached,
                "fetched": cached,
                "available": True,
                "coverage": derive_news_coverage_score(
                    cached, minimum_items=minimum_items
                ),
                "freshness": derive_news_freshness_score(
                    cached,
                    stale_after_days=float(requirements.get("stale_after_days", 2)),
                ),
                "source": "vector_db_load",
                "error": None,
                "performed_network_fetch": False,
                "should_persist": False,
            }

        if dataset == "macro":
            macro_result = materialize_macro_dataset(requirements, dataset_state)
            if macro_result is None:
                return None
            return {
                "dataset": dataset,
                "dataset_state": dataset_state,
                "dataset_payload": macro_result["dataset_payload"],
                "fetched": macro_result["fetched"],
                "available": bool(macro_result["available"]),
                "coverage": float(macro_result["coverage"]),
                "freshness": float(macro_result["freshness"]),
                "source": str(macro_result["source"]),
                "error": None,
                "performed_network_fetch": False,
                "should_persist": False,
            }
    except Exception as exc:  # noqa: BLE001
        context["materialize_error"] = str(exc)

    return None


async def fetch_or_refresh_dataset(
    context: DatasetOperationContext,
) -> DatasetOperationResult:
    dataset = context["dataset"]
    requirements = context["requirements"]
    dataset_state = dict(context["dataset_state"])
    symbols = context["symbols"]
    ticker = context["ticker"]
    error = context.get("materialize_error")

    try:
        if dataset == "ohlcv" and symbols:
            by_symbol, payload_by_symbol = fetch_ohlcv_by_symbol(symbols, requirements)
            available, coverage, freshness = _summarize_by_symbol(by_symbol)
            dataset_state["by_symbol"] = by_symbol
            dataset_payload = {"by_symbol": payload_by_symbol}
            return {
                "dataset": dataset,
                "dataset_state": dataset_state,
                "dataset_payload": dataset_payload,
                "fetched": dataset_payload,
                "available": available,
                "coverage": coverage,
                "freshness": freshness,
                "source": "fetch_attempt",
                "error": error,
                "performed_network_fetch": True,
                "should_persist": True,
            }

        if dataset == "fundamentals" and symbols:
            by_symbol, payload_by_symbol = fetch_fundamentals_by_symbol(
                symbols, requirements
            )
            available, coverage, freshness = _summarize_by_symbol(by_symbol)
            dataset_state["by_symbol"] = by_symbol
            dataset_payload = {"by_symbol": payload_by_symbol}
            return {
                "dataset": dataset,
                "dataset_state": dataset_state,
                "dataset_payload": dataset_payload,
                "fetched": dataset_payload,
                "available": available,
                "coverage": coverage,
                "freshness": freshness,
                "source": "fetch_attempt",
                "error": error,
                "performed_network_fetch": True,
                "should_persist": True,
            }

        if dataset == "news":
            fetched = await _fetch_planned_news(
                objective=news_dataset.build_news_objective(
                    context["goal"],
                    context["query"],
                    symbols,
                    ticker,
                ),
                ticker=ticker,
                company_name=resolve_company_name(context["goal"]),
                timeframe=context["timeframe"],
                conversation_history=context["conversation_history"],
                goal=context["goal"],
            )
            available = bool(fetched)
            return {
                "dataset": dataset,
                "dataset_state": dataset_state,
                "dataset_payload": fetched,
                "fetched": fetched,
                "available": available,
                "coverage": (
                    derive_news_coverage_score(
                        fetched,
                        minimum_items=int(requirements.get("minimum_items", 10)),
                    )
                    if available
                    else float(dataset_state.get("coverage", 0.0))
                ),
                "freshness": (
                    derive_news_freshness_score(
                        fetched,
                        stale_after_days=float(requirements.get("stale_after_days", 2)),
                    )
                    if available
                    else float(dataset_state.get("freshness", 0.0))
                ),
                "source": "fetch_attempt",
                "error": error,
                "performed_network_fetch": True,
                "should_persist": available and fetched is not None,
            }

        if dataset == "macro":
            macro_result = fetch_macro_dataset(requirements)
            return {
                "dataset": dataset,
                "dataset_state": dataset_state,
                "dataset_payload": macro_result["dataset_payload"],
                "fetched": macro_result["fetched"],
                "available": bool(macro_result["available"]),
                "coverage": float(macro_result["coverage"]),
                "freshness": float(macro_result["freshness"]),
                "source": str(macro_result["source"]),
                "error": error,
                "performed_network_fetch": True,
                "should_persist": bool(macro_result["available"]),
            }
    except Exception as exc:  # noqa: BLE001
        error = str(exc)

    return {
        "dataset": dataset,
        "dataset_state": dataset_state,
        "dataset_payload": context["dataset_payload"],
        "fetched": None,
        "available": False,
        "coverage": float(dataset_state.get("coverage", 0.0)),
        "freshness": float(dataset_state.get("freshness", 0.0)),
        "source": "fetch_attempt",
        "error": error,
        "performed_network_fetch": True,
        "should_persist": False,
    }


def persist_dataset_result(
    result: DatasetOperationResult, ticker: str | None
) -> dict[str, Any] | None:
    if not result["should_persist"]:
        return None

    dataset_payload = result["dataset_payload"]
    return _store_data(
        dataset=result["dataset"],
        payload=result["fetched"],
        ticker=ticker,
        payload_by_symbol=(
            dataset_payload.get("by_symbol")
            if isinstance(dataset_payload, dict)
            else None
        ),
    )


def apply_dataset_result(
    *,
    result: DatasetOperationResult,
    current_status: dict[str, Any],
    touched_data_status: dict[str, dict[str, Any]],
    fetched_data: dict[str, Any],
    persistence_outcome: dict[str, Any] | None = None,
) -> bool:
    dataset = result["dataset"]
    dataset_state = dict(result["dataset_state"])
    dataset_state["available"] = result["available"]
    dataset_state.setdefault("partial", True)
    dataset_state["source"] = result["source"]
    dataset_state["coverage"] = result["coverage"]
    dataset_state["freshness"] = result["freshness"]
    persistence_error = None
    if persistence_outcome is not None and not bool(persistence_outcome.get("ok")):
        persistence_error = str(persistence_outcome.get("error") or "PERSISTENCE_FAILED")
    dataset_state["error"] = persistence_error or (
        result["error"]
        if result["error"]
        else (None if result["available"] else "INSUFFICIENT_DATA")
    )

    current_status[dataset] = dataset_state
    touched_data_status[dataset] = dataset_state
    fetched_data[dataset] = result["dataset_payload"]
    return bool(result["performed_network_fetch"])


@observe(name="Data:Fetch", as_type="span")
async def data_fetch_node(state: dict[str, Any]) -> dict[str, Any]:
    current_status = dict(state.get("data_status", {}))
    fetched_data = dict(state.get("fetched_data", {}))
    data_plan = state.get("data_plan", [])
    touched_data_status: dict[str, dict[str, Any]] = {}
    retries = dict(state.get("retry_count_by_domain", {}))
    performed_network_fetch = False

    goal = dict(state.get("goal", {}))
    extracted = extract_goal_symbols(goal)
    raw_ticker = goal.get("ticker")
    if isinstance(raw_ticker, str) and raw_ticker.strip():
        primary_symbol = raw_ticker.strip().upper()
    else:
        primary_symbol = extracted[0] if extracted else None

    symbols = (
        [primary_symbol]
        if isinstance(primary_symbol, str) and primary_symbol.strip()
        else []
    )
    ticker = primary_symbol
    query = state.get("user_query", "")
    timeframe_policy = dict(state.get("timeframe_policy", {}))

    if _required_status_ready_for_materialization(
        current_status, timeframe_policy
    ) and not _required_payloads_materialized(fetched_data):
        data_plan = _build_materialize_plan(timeframe_policy)
    elif not isinstance(data_plan, list) or not data_plan:
        data_plan = _build_materialize_plan(timeframe_policy)

    for item in data_plan:
        if not item.get("dataset"):
            continue

        context = build_operation_context(
            state=state,
            item=item,
            timeframe_policy=timeframe_policy,
            symbols=symbols,
            ticker=ticker,
            goal=goal,
            query=query,
        )

        result = (
            materialize_dataset(context) if context["action"] == "materialize" else None
        )
        if result is None:
            result = await fetch_or_refresh_dataset(context)

        persistence_outcome = persist_dataset_result(result, ticker)
        performed_network_fetch = (
            apply_dataset_result(
                result=result,
                current_status=current_status,
                touched_data_status=touched_data_status,
                fetched_data=fetched_data,
                persistence_outcome=persistence_outcome,
            )
            or performed_network_fetch
        )

    if performed_network_fetch:
        retries["data_fetch"] = retries.get("data_fetch", 0) + 1

    opik_context.update_current_span(
        metadata={
            "performed_network_fetch": performed_network_fetch,
            "datasets_touched": list(touched_data_status.keys()),
        }
    )

    payload = {
        "data_status": current_status,
        "fetched_data": fetched_data,
        "retry_count_by_domain": retries,
        "status": "partial",
        "reasoning": "Recorded deterministic fetch attempts and updated dataset statuses.",
        "confidence_score": 0.5,
        "next_action": "run_data_check",
        "data": {"data_status": current_status, "fetched_data": fetched_data},
        "errors": [],
    }
    payload["data"]["audit"] = _build_data_fetch_audit(
        state, payload, data_plan, touched_data_status
    )
    return finalize_node_output("data_fetch_node", payload)
