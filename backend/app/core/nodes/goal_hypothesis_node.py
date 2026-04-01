from __future__ import annotations

from typing import Any


async def goal_hypothesis_node(state: dict[str, Any]) -> dict[str, Any]:
    user_query = state.get("user_query", "")

    goal = {
        "objective": user_query,
        "scope": "financial_research",
        "constraints": ["no_hallucinated_data", "deterministic_confidence"],
        "success_criteria": "validated structured output",
    }
    hypotheses = [
        {
            "id": "h1",
            "statement": "Current market and fundamental signals can support a directional view.",
            "rationale": "Use available datasets to evaluate directional bias.",
            "priority": "P0",
        }
    ]

    return {
        "status": "success",
        "reasoning": "Converted user intent into a concrete goal and initial hypothesis set.",
        "confidence_score": 0.75,
        "next_action": "run_data_check",
        "data": {"goal": goal, "hypotheses": hypotheses},
        "errors": [],
    }
