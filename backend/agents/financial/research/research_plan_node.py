"""Research planner node."""

from __future__ import annotations

from typing import Any

from app.core.contracts.graph_node import finalize_node_output
from agents.shared.utils import (
    DEFAULT_TASK_TEMPLATES,
    selected_agents,
    task_sort_key,
    extract_goal_symbols,
)
from app.services.embedding_service import EmbeddingService
from app.core.node_resources import resources


def _primary_symbol_payload(payload: dict[str, Any], symbol: str | None) -> Any:
    if not isinstance(payload, dict):
        return payload
    by_symbol = payload.get("by_symbol")
    if isinstance(by_symbol, dict) and symbol:
        return by_symbol.get(symbol) or by_symbol.get(symbol.upper())
    return payload


def _task_specific_parameters(
    agent: str,
    ticker: str | None,
    fetched_data: dict[str, Any],
    query: str,
    rag_context: str = "",
    rag_chunks: list[Any] | None = None,
) -> dict[str, Any]:
    ohlcv_payload = _primary_symbol_payload(fetched_data.get("ohlcv", {}), ticker)
    fundamentals_payload = _primary_symbol_payload(
        fetched_data.get("fundamentals", {}), ticker
    )
    macro_payload = fetched_data.get("macro", {})

    if agent == "fundamental_analysis":
        return {"raw_data": fundamentals_payload or {}}
    if agent == "technical_analysis":
        if isinstance(ohlcv_payload, dict):
            return {"ohlcv_data": ohlcv_payload.get("data", [])}
        return {"ohlcv_data": []}
    if agent == "sentiment_analysis":
        return {
            "text": rag_context
            or "Insufficient qualitative evidence found for research analysis."
        }
    if agent == "macro_analysis":
        return {"macro_data": macro_payload or {}}
    if agent == "contrarian_analysis":
        market_data = {
            "ohlcv": ohlcv_payload or {},
            "fundamentals": fundamentals_payload or {},
            "macro": macro_payload or {},
        }
        sentiment_data = []
        if rag_chunks:
            sentiment_data = [
                {
                    "title": "RAG News Context",
                    "summary": chunk.text,
                    "content": chunk.text,
                    "source": chunk.metadata.get(
                        "source", chunk.metadata.get("domain", "Unknown")
                    ),
                    "published_date": chunk.metadata.get(
                        "published_date", chunk.metadata.get("date", "")
                    ),
                }
                for chunk in rag_chunks
            ]
        else:
            sentiment_data = [
                {
                    "title": "Insufficient Data",
                    "summary": "Insufficient qualitative evidence found for research analysis",
                    "content": "Insufficient qualitative evidence found for research analysis",
                    "source": "None",
                    "published_date": "",
                }
            ]
        return {
            "market_data": market_data,
            "sentiment_data": sentiment_data,
        }
    return {}


async def research_plan_node(state: dict[str, Any]) -> dict[str, Any]:
    goal = dict(state.get("goal", {}))
    symbols = extract_goal_symbols(goal)
    ticker = symbols[0] if symbols else None
    query = state.get("user_query", "")
    timeframe = state.get("timeframe")
    selected = set(selected_agents(state))
    fetched_data = dict(state.get("fetched_data", {}))

    rag_context = ""
    rag_chunks = []
    if any(agent in selected for agent in ["sentiment_analysis", "contrarian_analysis"]):
        try:
            embedding_service = EmbeddingService()
            query_embedding = embedding_service.embed_text(query)
            chunks = resources.vector_db.search(
                query_embedding=query_embedding,
                query_text=query,
                ticker=ticker,
                limit=10,
            )
            if chunks:
                rag_chunks = chunks
                parts = []
                for c in chunks:
                    source = c.metadata.get(
                        "source", c.metadata.get("domain", "Unknown")
                    )
                    date = c.metadata.get("published_date", c.metadata.get("date", ""))
                    parts.append(f"Source: {source} ({date})\nContent: {c.text}")
                rag_context = "\n\n---\n\n".join(parts)
        except Exception:
            # Fallback will be handled by passing empty rag_context to _task_specific_parameters
            pass

    tasks = list(state.get("replanned_tasks", []))
    if not tasks:
        tasks = []
        for template in DEFAULT_TASK_TEMPLATES:
            if template["agent"] not in selected:
                continue
            tasks.append(
                {
                    "task_id": template["task_id"],
                    "agent": template["agent"],
                    "priority": template["priority"],
                    "parameters": {
                        "ticker": ticker,
                        "symbols": symbols,
                        "query": query,
                        "timeframe": timeframe,
                        **_task_specific_parameters(
                            template["agent"],
                            ticker,
                            fetched_data,
                            query,
                            rag_context,
                            rag_chunks,
                        ),
                    },
                }
            )
    else:
        filtered_tasks: list[dict[str, Any]] = []
        for task in tasks:
            if task.get("agent") not in selected:
                continue
            parameters = task.setdefault("parameters", {})
            if "symbols" not in parameters:
                parameters["symbols"] = symbols
            if "ticker" not in parameters:
                parameters["ticker"] = ticker
            if "query" not in parameters:
                parameters["query"] = query
            if "timeframe" not in parameters:
                parameters["timeframe"] = timeframe
            parameters.update(
                {
                    key: value
                    for key, value in _task_specific_parameters(
                        task.get("agent", ""),
                        ticker,
                        fetched_data,
                        query,
                        rag_context,
                        rag_chunks,
                    ).items()
                    if key not in parameters
                }
            )
            filtered_tasks.append(task)
        tasks = filtered_tasks

    tasks = sorted(tasks, key=task_sort_key)
    payload = {
        "tasks": tasks,
        "force_replan": False,
        "replanned_tasks": [],
        "status": "success",
        "reasoning": "Built prioritized research tasks from goal and hypotheses.",
        "confidence_score": float(state.get("confidence_score", 0.6)),
        "next_action": "run_research_execution",
        "data": {"tasks": tasks},
        "errors": [],
    }
    return finalize_node_output("research_plan_node", payload)
