from __future__ import annotations

from typing import Any

from app.core.router_policy import EVIDENCE_STRENGTH_THRESHOLD


def _moving_average(values: list[float], window: int = 3) -> float:
    if not values:
        return 0.0
    sample = values[-window:]
    return sum(sample) / len(sample)


async def critic_node(state: dict[str, Any]) -> dict[str, Any]:
    evidence_strength = float(state.get("evidence_strength", 0.0))
    synthesis_confidence = float(state.get("synthesis_confidence", 0.0))
    freshness_penalty = float(state.get("confidence_components", {}).get("freshness_penalty", 0.0))
    contradiction_penalty = float(state.get("confidence_components", {}).get("contradiction_penalty", 0.0))

    decision = "approve"
    if state.get("critic_decision") == "conflict":
        decision = "conflict"
    elif evidence_strength < EVIDENCE_STRENGTH_THRESHOLD:
        decision = "retry"

    adjusted = max(0.0, synthesis_confidence - freshness_penalty - contradiction_penalty)
    history = list(state.get("confidence_history", [])) + [adjusted]
    smoothed = _moving_average(history)

    return {
        "status": "success",
        "reasoning": "Evaluated synthesis quality, evidence strength, and contradiction/freshness penalties.",
        "confidence_score": smoothed,
        "next_action": "run_validation" if decision == "approve" else "run_reflection",
        "data": {
            "decision": decision,
            "adjusted_confidence": adjusted,
            "smoothed_confidence": smoothed,
        },
        "critic_decision": decision,
        "adjusted_confidence": adjusted,
        "confidence_history": history,
        "smoothed_confidence": smoothed,
        "errors": [],
    }
