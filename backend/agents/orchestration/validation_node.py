from __future__ import annotations

from typing import Any

from app.core.contracts.graph_node import finalize_node_output
from app.core.audit import build_node_audit_entry
from app.core.node_resources import resources
from app.core.observability import observe, opik_context
from app.core.report_renderer import generate_narrative_report
from app.core.research_quality import evaluate_research_gate
from agents.quality.claim_verifier import is_data_gap_claim


@observe(name="Quality:ValidationGate", as_type="span")
async def validation_node(state: dict[str, Any]) -> dict[str, Any]:
    synthesis = state.get("results", {}).get("synthesis", {})
    if not isinstance(synthesis, dict) or not synthesis:
        payload: dict[str, Any] = {
            "status": "failure",
            "reasoning": "Validation failed: synthesis payload is missing.",
            "confidence_score": float(state.get("confidence_score", 0.0)),
            "next_action": "terminate_failure",
            "data": {},
            "errors": ["Missing synthesis payload"],
            "validation_passed": False,
        }
        audit = build_node_audit_entry("validation_node", state, payload)
        audit["decision_summary"] = {
            "gate_result": "hard_stop",
            "hard_stop_reason": "missing_synthesis",
            "final_decision": "none",
            "final_confidence": 0.0,
        }
        payload["data"]["audit"] = audit
        return finalize_node_output("validation_node", payload)

    claims = synthesis.get("claims", [])

    missing_evidence = [
        c.get("claim_id")
        for c in claims
        if isinstance(c, dict)
        and not c.get("evidence_refs")
        and not is_data_gap_claim(c.get("text", ""))
    ]
    if missing_evidence:
        payload = {
            "status": "failure",
            "reasoning": "Validation failed: claims missing evidence references.",
            "confidence_score": float(state.get("confidence_score", 0.0)),
            "next_action": "terminate_failure",
            "data": {"missing_evidence_claim_ids": missing_evidence},
            "errors": [
                f"Missing evidence_refs for claim_id={claim_id}"
                for claim_id in missing_evidence
            ],
            "validation_passed": False,
        }
        audit = build_node_audit_entry("validation_node", state, payload)
        audit["decision_summary"] = {
            "gate_result": "hard_stop",
            "hard_stop_reason": "missing_claim_evidence",
            "final_decision": "none",
            "final_confidence": 0.0,
            "missing_evidence_claim_ids": missing_evidence,
        }
        payload["data"]["audit"] = audit
        return finalize_node_output("validation_node", payload)

    major_claims = [c for c in claims if c.get("importance") == "major"]
    verified_claim_ids = set(
        (state.get("claim_verification") or {}).get("verified_claim_ids", [])
    )
    verified_major_claims = [
        c for c in major_claims if c.get("claim_id") in verified_claim_ids
    ]

    unresolved_conflicts = state.get("conflict_record", {}).get(
        "unresolved_claim_pairs", []
    )

    gate = evaluate_research_gate(
        required_agents=state.get("required_agents", state.get("approved_agents", [])),
        completed_agents=list(state.get("results", {}).keys()),
        major_claim_count=len(major_claims),
        verified_major_claim_count=len(verified_major_claims),
        evidence_strength=float(state.get("evidence_strength", 0.0)),
        source_diversity=float(
            state.get("coverage_report", {}).get("source_diversity_score", 0.5)
        ),
        unresolved_conflicts=len(unresolved_conflicts),
    )

    opik_context.update_current_span(
        metadata={
            "gate_status": gate.status,
            "gate_code": gate.code,
            "major_claims": len(major_claims),
            "verified_major_claims": len(verified_major_claims),
        }
    )

    if gate.status == "hard_stop":
        payload = {
            "status": "failure",
            "reasoning": f"Validation failed quality gate: {gate.message}",
            "confidence_score": float(state.get("confidence_score", 0.0)),
            "next_action": "terminate_failure",
            "data": {"gate_result": gate.__dict__},
            "errors": [gate.message],
            "validation_passed": False,
        }
        audit = build_node_audit_entry("validation_node", state, payload)
        audit["decision_summary"] = {
            "gate_result": "hard_stop",
            "hard_stop_reason": gate.message,
            "final_decision": "none",
            "final_confidence": 0.0,
        }
        payload["data"]["audit"] = audit
        return finalize_node_output("validation_node", payload)

    confidence_score = float(state.get("confidence_score", 0.0))
    final_confidence = float(min(1.0, max(0.0, confidence_score)))

    insufficiency_markers = list(synthesis.get("insufficiency_markers", []))
    if not state.get("goal"):
        insufficiency_markers.append("goal_missing")

    final_output = {
        "status": (
            "success"
            if gate.status == "pass" and not insufficiency_markers
            else "insufficient_data"
        ),
        "decision": synthesis.get("decision", "no_call"),
        "confidence_score": confidence_score,
        "final_confidence": final_confidence,
        "key_drivers": synthesis.get("key_drivers", []),
        "risks": synthesis.get("risks", []),
        "data_used": state.get("data_status", {}),
        "insufficiency_markers": insufficiency_markers,
        "reasoning": gate.message,
        "next_action": "complete",
    }
    final_report = await generate_narrative_report(
        state,
        resources,
        terminal_output=final_output,
        is_low_confidence=False,
        reason=gate.message,
    )

    payload = {
        "status": "success",
        "reasoning": "Validation completed with explicit quality gate check.",
        "confidence_score": confidence_score,
        "next_action": "run_evaluator",
        "data": {"final_output": final_output, "gate_result": gate.__dict__},
        "validation_passed": True,
        "final_output": final_output,
        "final_confidence": final_confidence,
        "final_report": final_report,
        "errors": [],
    }

    audit = build_node_audit_entry("validation_node", state, payload)
    audit["decision_summary"] = {
        "gate_result": gate.status,
        "hard_stop_reason": None,
        "final_decision": final_output.get("decision"),
        "final_confidence": final_confidence,
    }
    payload["data"]["audit"] = audit

    return finalize_node_output("validation_node", payload)
