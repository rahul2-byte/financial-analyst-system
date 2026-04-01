from __future__ import annotations

from typing import Any


async def autonomous_conflict_resolution_node(state: dict[str, Any]) -> dict[str, Any]:
    results = dict(state.get("results", {}))
    synthesis = dict(results.get("synthesis", {}))
    synthesis["risks"] = list(synthesis.get("risks", [])) + [
        "conflicting signals required arbitration"
    ]
    results["synthesis"] = synthesis
    results["conflict_resolution"] = {
        "resolved": True,
        "method": "recency_and_evidence_weighting",
    }

    return {
        "results": results,
        "critic_decision": None,
        "status": "success",
        "reasoning": "Resolved conflict and forced re-synthesis/critic cycle.",
        "confidence_score": float(state.get("confidence_score", 0.0)),
        "next_action": "run_synthesis",
        "data": {"conflict_resolution": results["conflict_resolution"]},
        "errors": [],
    }
