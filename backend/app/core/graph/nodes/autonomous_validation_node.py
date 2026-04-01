from __future__ import annotations

import json
from typing import Any


REQUIRED_FIELDS = {
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
    if not isinstance(synthesis, dict) or not synthesis:
        return {
            "status": "failure",
            "reasoning": "Validation failed: synthesis payload is missing.",
            "confidence_score": float(state.get("confidence_score", 0.0)),
            "next_action": "terminate_failure",
            "data": {},
            "errors": ["Missing synthesis payload"],
            "validation_passed": False,
        }

    claims = synthesis.get("claims", [])
    if not isinstance(claims, list):
        return {
            "status": "failure",
            "reasoning": "Validation failed: synthesis claims must be a list.",
            "confidence_score": float(state.get("confidence_score", 0.0)),
            "next_action": "terminate_failure",
            "data": {},
            "errors": ["Invalid synthesis claims shape"],
            "validation_passed": False,
        }

    missing_claim_evidence = [
        claim.get("claim_id", "unknown")
        for claim in claims
        if not isinstance(claim, dict)
        or not isinstance(claim.get("evidence_refs", []), list)
        or len(claim.get("evidence_refs", [])) == 0
    ]
    if missing_claim_evidence:
        return {
            "status": "failure",
            "reasoning": "Validation failed: one or more claims have no evidence references.",
            "confidence_score": float(state.get("confidence_score", 0.0)),
            "next_action": "terminate_failure",
            "data": {},
            "errors": [
                f"Claims missing evidence refs: {sorted(str(c) for c in missing_claim_evidence)}"
            ],
            "validation_passed": False,
        }

    confidence_score = float(state.get("confidence_score", 0.0))
    final_confidence = float(min(1.0, max(0.0, confidence_score)))

    insufficiency_markers = list(synthesis.get("insufficiency_markers", []))
    if not state.get("goal"):
        insufficiency_markers.append("goal_missing")

    final_output = {
        "status": "success"
        if confidence_score >= 0.75 and not insufficiency_markers
        else "insufficient_data",
        "decision": synthesis.get("decision", "no_call"),
        "confidence_score": confidence_score,
        "final_confidence": final_confidence,
        "key_drivers": synthesis.get("key_drivers", []),
        "risks": synthesis.get("risks", []),
        "data_used": synthesis.get("data_used", {}),
        "insufficiency_markers": insufficiency_markers,
        "reasoning": "Validation confirmed output contract and data sufficiency markers.",
        "next_action": "complete",
    }

    missing = REQUIRED_FIELDS - set(final_output)
    if missing:
        return {
            "status": "failure",
            "reasoning": "Validation failed: output contract incomplete.",
            "confidence_score": confidence_score,
            "next_action": "terminate_failure",
            "data": {},
            "errors": [f"Missing final output fields: {sorted(missing)}"],
            "validation_passed": False,
        }

    return {
        "status": "success",
        "reasoning": "Validation completed with explicit insufficiency handling.",
        "confidence_score": confidence_score,
        "next_action": "terminate_success" if final_output["status"] == "success" else "terminate_insufficient_data",
        "data": {"final_output": final_output},
        "validation_passed": True,
        "final_output": final_output,
        "final_confidence": final_confidence,
        "final_report": json.dumps(final_output, ensure_ascii=True),
        "errors": [],
    }
