from __future__ import annotations

from typing import Any


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


async def synthesis_node(state: dict[str, Any]) -> dict[str, Any]:
    results = state.get("results", {})
    confidences = [
        float(results.get("fundamental", {}).get("confidence", 0.0)),
        float(results.get("sentiment", {}).get("confidence", 0.0)),
        float(results.get("macro", {}).get("confidence", 0.0)),
    ]
    synthesis_confidence = _mean(confidences)

    synthesis = {
        "decision": "watchlist",
        "key_drivers": ["mixed macro backdrop", "moderate sentiment support"],
        "risks": ["data staleness", "conflicting directional signals"],
        "data_used": state.get("data_status", {}),
    }

    return {
        "status": "success",
        "reasoning": "Synthesized cross-agent findings into a single structured view.",
        "confidence_score": synthesis_confidence,
        "next_action": "run_critic",
        "data": {"synthesis": synthesis, "synthesis_confidence": synthesis_confidence},
        "results": {"synthesis": synthesis},
        "synthesis_confidence": synthesis_confidence,
        "errors": [],
    }
