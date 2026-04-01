from __future__ import annotations

from typing import Any

from app.core.graph.nodes.autonomous_quality.evidence import (
    evidence_ref_set,
    evidence_strength_from_outputs,
    mean,
    signal_from_text,
    top_metric_drivers,
)


async def autonomous_synthesis_node(state: dict[str, Any]) -> dict[str, Any]:
    results = state.get("results", {})
    tool_registry = state.get("tool_registry", [])
    supported_agents = ["fundamental_analysis", "sentiment_analysis", "macro_analysis"]
    signals = [signal_from_text(results.get(agent, "")) for agent in supported_agents]

    bullish = sum(1 for s in signals if s == "bullish")
    bearish = sum(1 for s in signals if s == "bearish")

    decision = "watchlist"
    if bullish > bearish:
        decision = "buy"
    elif bearish > bullish:
        decision = "sell"

    evidence_strength = evidence_strength_from_outputs(results, tool_registry)
    synthesis_confidence = mean([0.6 + evidence_strength * 0.2, 0.55 + evidence_strength * 0.2])

    key_drivers = [f"signal_mix={signals}"] + top_metric_drivers(tool_registry)
    all_refs = sorted(evidence_ref_set(tool_registry))
    claims = [
        {
            "claim_id": "c1",
            "text": "Cross-agent signal synthesis supports provisional directional thesis.",
            "evidence_refs": all_refs[: min(3, len(all_refs))],
        }
    ]

    synthesis = {
        "decision": decision,
        "key_drivers": key_drivers,
        "claims": claims,
        "risks": ["partial evidence", "data freshness constraints"],
        "data_used": state.get("data_status", {}),
        "insufficiency_markers": [
            dataset
            for dataset, status in state.get("data_status", {}).items()
            if not status.get("available", False)
        ],
    }

    return {
        "results": {**results, "synthesis": synthesis},
        "evidence_strength": evidence_strength,
        "synthesis_confidence": synthesis_confidence,
        "status": "success",
        "reasoning": "Synthesized agent signals with deterministic confidence weighting.",
        "confidence_score": synthesis_confidence,
        "next_action": "run_critic",
        "data": {"synthesis": synthesis},
        "errors": [],
    }
