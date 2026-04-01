from __future__ import annotations

from typing import Any

from app.core.contracts.graph_node import finalize_node_output
from app.core.graph.nodes.autonomous_quality.evidence import (
    build_contradiction_records,
    evidence_count_by_agent,
    evidence_ref_set,
    horizon_from_text,
    intensity_from_text,
    moving_average,
    signal_from_text,
    validate_claim_evidence_links,
)
from app.core.graph.router_policy import EVIDENCE_STRENGTH_THRESHOLD


async def autonomous_critic_node(state: dict[str, Any]) -> dict[str, Any]:
    synthesis = state.get("results", {}).get("synthesis", {})
    synthesis_claims = synthesis.get("claims", [])
    data_used = synthesis.get("data_used", {})
    stale_count = sum(
        1 for status in data_used.values() if float(status.get("freshness", 0.0)) < 0.6
    )
    tool_registry = state.get("tool_registry", [])
    evidence_counts = evidence_count_by_agent(tool_registry)

    agent_claims = [
        {
            "agent": "fundamental_analysis",
            "direction": signal_from_text(state.get("results", {}).get("fundamental_analysis", "")),
            "horizon": horizon_from_text(state.get("results", {}).get("fundamental_analysis", "")),
            "intensity": intensity_from_text(state.get("results", {}).get("fundamental_analysis", "")),
            "evidence_count": evidence_counts.get("fundamental_analysis", 0),
        },
        {
            "agent": "sentiment_analysis",
            "direction": signal_from_text(state.get("results", {}).get("sentiment_analysis", "")),
            "horizon": horizon_from_text(state.get("results", {}).get("sentiment_analysis", "")),
            "intensity": intensity_from_text(state.get("results", {}).get("sentiment_analysis", "")),
            "evidence_count": evidence_counts.get("sentiment_analysis", 0),
        },
        {
            "agent": "macro_analysis",
            "direction": signal_from_text(state.get("results", {}).get("macro_analysis", "")),
            "horizon": horizon_from_text(state.get("results", {}).get("macro_analysis", "")),
            "intensity": intensity_from_text(state.get("results", {}).get("macro_analysis", "")),
            "evidence_count": evidence_counts.get("macro_analysis", 0),
        },
    ]

    contradiction_records = build_contradiction_records(agent_claims)
    max_contradiction_severity = max(
        (float(record["severity"]) for record in contradiction_records), default=0.0
    )
    contradiction_penalty = min(0.35, max_contradiction_severity * 0.4)

    ref_set = evidence_ref_set(tool_registry)
    hallucination_issues = (
        validate_claim_evidence_links(synthesis_claims, ref_set)
        if isinstance(synthesis_claims, list)
        else []
    )

    hallucination_penalty = 0.2 if hallucination_issues else 0.0
    freshness_penalty = 0.05 * stale_count

    synthesis_confidence = float(state.get("synthesis_confidence", 0.0))
    adjusted_confidence = max(
        0.0,
        synthesis_confidence - freshness_penalty - contradiction_penalty - hallucination_penalty,
    )
    history = list(state.get("confidence_history", [])) + [adjusted_confidence]
    smoothed_confidence = moving_average(history)

    evidence_strength = float(state.get("evidence_strength", 0.0))
    decision = "approve"
    if evidence_strength < EVIDENCE_STRENGTH_THRESHOLD:
        decision = "retry"

    if any(
        record["type"] != "evidence_gap" and float(record["severity"]) >= 0.45
        for record in contradiction_records
    ):
        decision = "conflict"
    elif any(record["type"] == "evidence_gap" for record in contradiction_records):
        decision = "retry"

    if hallucination_issues:
        decision = "retry"

    payload = {
        "critic_decision": decision,
        "hallucination_issues": hallucination_issues,
        "contradiction_records": contradiction_records,
        "adjusted_confidence": adjusted_confidence,
        "smoothed_confidence": smoothed_confidence,
        "confidence_score": smoothed_confidence,
        "confidence_history": history,
        "confidence_components": {
            "freshness_penalty": freshness_penalty,
            "contradiction_penalty": contradiction_penalty,
            "hallucination_penalty": hallucination_penalty,
            "max_contradiction_severity": max_contradiction_severity,
        },
        "status": "success",
        "reasoning": "Applied evidence and consistency checks to synthesized output.",
        "next_action": "run_validation" if decision == "approve" else "run_reflection",
        "data": {"critic_decision": decision},
        "errors": [],
    }
    return finalize_node_output("autonomous_critic_node", payload)
