from __future__ import annotations

import logging
from typing import Any

from app.core.contracts.graph_node import finalize_node_output
from app.core.audit import build_node_audit_entry
from app.core.observability import observe, opik_context
from agents.quality.evidence import (
    evidence_strength_from_outputs,
    mean,
)

logger = logging.getLogger(__name__)


@observe(name="Quality:Synthesis", as_type="span")
async def synthesis_node(state: dict[str, Any]) -> dict[str, Any]:
    results = state.get("results", {})
    tool_registry = state.get("tool_registry", [])
    claim_verification = state.get("claim_verification")

    verified_claim_ids = set(
        claim_verification.get("verified_claim_ids", [])
        if isinstance(claim_verification, dict)
        else []
    )

    all_claims = []
    for agent, result in results.items():
        if isinstance(result, dict) and "claims" in result:
            claims = result.get("claims", [])
            if not isinstance(claims, list):
                continue
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                all_claims.append({**claim, "source_agent": agent})

    is_provisional_pass = claim_verification is None
    synthesis_claims = (
        all_claims
        if is_provisional_pass
        else [
            claim for claim in all_claims if claim.get("claim_id") in verified_claim_ids
        ]
    )

    # Heuristic decision based on verified claims' importance and sentiment (if we had sentiment on claims)
    # For now, let's stick to a simpler aggregation of verified claims.

    major_claims = [c for c in synthesis_claims if c.get("importance") == "major"]

    # Simple decision logic based on major claims presence
    if major_claims:
        # If there are major claims, we might have enough to make a call
        decision = "watchlist"  # Default to watchlist if we can't determine directionality easily
        # In a real implementation, we'd use an LLM to synthesize the prose or more complex logic
    else:
        decision = "no_call"

    state_evidence_strength = state.get("evidence_strength")
    if state_evidence_strength in (None, 0.0):
        evidence_strength = evidence_strength_from_outputs(results, tool_registry)
    else:
        evidence_strength = float(state_evidence_strength)

    if not is_provisional_pass and not synthesis_claims:
        evidence_strength = 0.0

    synthesis_confidence = mean(
        [0.6 + evidence_strength * 0.2, 0.55 + evidence_strength * 0.2]
    )

    opik_context.update_current_span(
        metadata={
            "evidence_strength": evidence_strength,
            "provisional_claims": len(synthesis_claims) if is_provisional_pass else 0,
            "verified_claims": len(synthesis_claims) if not is_provisional_pass else 0,
        }
    )

    key_drivers = (
        [c.get("text") for c in major_claims]
        if major_claims
        else ["Insufficient verified major claims"]
    )

    synthesis = {
        "decision": decision,
        "key_drivers": key_drivers,
        "claims": synthesis_claims,
        "risks": [
            r
            for res in results.values()
            if isinstance(res, dict)
            for r in res.get("risks", [])
        ],
        "data_used": state.get("data_status", {}),
        "insufficiency_markers": [
            dataset
            for dataset, status in state.get("data_status", {}).items()
            if not status.get("available", False)
        ],
    }

    payload: dict[str, Any] = {
        "results": {**results, "synthesis": synthesis},
        "evidence_strength": evidence_strength,
        "synthesis_confidence": synthesis_confidence,
        "status": "success",
        "reasoning": (
            f"Synthesized research from {len(synthesis_claims)} provisional claims."
            if is_provisional_pass
            else f"Synthesized research from {len(synthesis_claims)} verified claims."
        ),
        "confidence_score": synthesis_confidence,
        "next_action": "run_critic",
        "data": {"synthesis": synthesis},
        "errors": [],
    }

    audit = build_node_audit_entry("synthesis_node", state, payload)
    audit["decision_summary"] = {
        "available_agents": list(results.keys()),
        "provisional_claim_count": len(synthesis_claims) if is_provisional_pass else 0,
        "verified_claim_count": len(synthesis_claims) if not is_provisional_pass else 0,
        "major_claim_count": len(major_claims),
        "evidence_strength": evidence_strength,
        "decision": decision,
        "insufficiency_markers_count": len(synthesis.get("insufficiency_markers", [])),
        "reasoning": payload["reasoning"],
    }
    payload["data"]["audit"] = audit

    return finalize_node_output("synthesis_node", payload)
