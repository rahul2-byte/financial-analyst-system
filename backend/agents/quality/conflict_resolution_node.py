from __future__ import annotations

from typing import Any

from app.core.audit import build_node_audit_entry
from app.core.contracts.graph_node import finalize_node_output


async def conflict_resolution_node(state: dict[str, Any]) -> dict[str, Any]:
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

    payload = {
        "results": results,
        "critic_decision": None,
        "status": "success",
        "reasoning": "Resolved conflict and forced re-synthesis/critic cycle.",
        "confidence_score": float(state.get("confidence_score", 0.0)),
        "next_action": "run_synthesis",
        "data": {"conflict_resolution": results["conflict_resolution"]},
        "errors": [],
    }

    audit = build_node_audit_entry("conflict_resolution_node", state, payload)
    audit["decision_summary"] = {
        "resolved": True,
        "resolution_method": "recency_and_evidence_weighting",
        "next_action": payload.get("next_action"),
        "synthesis_risk_count": len(synthesis.get("risks", [])),
    }
    payload["data"]["audit"] = audit

    return finalize_node_output("conflict_resolution_node", payload)
