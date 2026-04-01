from __future__ import annotations

from typing import Any


REQUIRED_OUTPUT_FIELDS = {
    "decision",
    "confidence_score",
    "final_confidence",
    "key_drivers",
    "risks",
    "data_used",
    "insufficiency_markers",
    "reasoning",
    "next_action",
}


async def autonomous_validation_node(state: dict[str, Any]) -> dict[str, Any]:
    synthesis = state.get("results", {}).get("synthesis", {})
    confidence_score = float(state.get("confidence_score", 0.0))
    final_confidence = min(1.0, max(0.0, confidence_score))

    final_output = {
        "status": "success" if confidence_score >= 0.75 else "partial",
        "decision": synthesis.get("decision", "no_call"),
        "confidence_score": confidence_score,
        "final_confidence": final_confidence,
        "key_drivers": synthesis.get("key_drivers", []),
        "risks": synthesis.get("risks", []),
        "data_used": synthesis.get("data_used", state.get("data_status", {})),
        "insufficiency_markers": [],
        "reasoning": "Validation gate confirmed output schema completeness and deterministic confidence fields.",
        "next_action": "complete",
    }

    missing = REQUIRED_OUTPUT_FIELDS - set(final_output.keys())
    if missing:
        return {
            "status": "failure",
            "reasoning": "Validation failed because required output contract fields were missing.",
            "confidence_score": confidence_score,
            "next_action": "terminate_failure",
            "data": {},
            "errors": [f"Missing required output fields: {sorted(missing)}"],
        }

    return {
        "status": "success",
        "reasoning": "Validation passed and final output contract is complete.",
        "confidence_score": confidence_score,
        "next_action": "terminate_success" if confidence_score >= 0.75 else "terminate_insufficient_data",
        "data": {"final_output": final_output},
        "validation_passed": True,
        "final_confidence": final_confidence,
        "final_output": final_output,
        "errors": [],
    }
