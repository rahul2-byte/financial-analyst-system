from __future__ import annotations

from typing import Any

from app.core.contracts.graph_node import finalize_node_output
from app.core.graph.ticker_extraction import extract_ticker


async def autonomous_goal_node(state: dict[str, Any]) -> dict[str, Any]:
    query = state.get("user_query", "")
    ticker = extract_ticker(query)

    goal = {
        "objective": query,
        "scope": "financial_research",
        "constraints": ["no_hallucinated_data", "deterministic_scoring"],
        "success_criteria": "validated structured final output",
        "ticker": ticker,
        "ticker_extraction_status": "resolved" if ticker else "unresolved",
    }

    hypotheses = [
        {
            "id": "h1",
            "statement": "Price action and fundamentals jointly support a directional thesis.",
            "rationale": "Cross-validate market structure with fundamentals.",
            "priority": "P0",
        },
        {
            "id": "h2",
            "statement": "Macro and sentiment can invalidate the directional thesis.",
            "rationale": "Use macro and news to detect regime risk.",
            "priority": "P1",
        },
    ]

    payload = {
        "goal": goal,
        "hypotheses": hypotheses,
        "status": "success",
        "reasoning": "Generated structured goal and hypotheses from user query.",
        "confidence_score": 0.7,
        "next_action": "run_data_check",
        "data": {"goal": goal, "hypotheses": hypotheses},
        "errors": [],
    }
    return finalize_node_output("autonomous_goal_node", payload)
