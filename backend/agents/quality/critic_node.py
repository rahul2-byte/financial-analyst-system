from __future__ import annotations

import logging
from typing import Any

from app.core.contracts.graph_node import finalize_node_output
from app.core.audit import build_node_audit_entry
from agents.quality.claim_verifier import is_data_gap_claim, verify_claims
from agents.quality.conflict_arbitrator import arbitrate_conflicts
from app.core.graph.router_policy import (
    CRITIC_RETRY_LIMIT,
    EVIDENCE_STRENGTH_THRESHOLD,
)

logger = logging.getLogger(__name__)


def _reprioritize_tasks(
    tasks: list[dict[str, Any]],
    error_type: str,
    correction_prompt: str | None,
) -> list[dict[str, Any]]:
    replanned: list[dict[str, Any]] = []
    for task in tasks:
        updated = dict(task)
        if updated.get("priority") in {"P1", "P2"}:
            updated["priority"] = "P0"
        params = dict(updated.get("parameters", {}))
        if correction_prompt:
            params["correction_prompt"] = correction_prompt
        if error_type in {"hallucination", "factual_error", "reasoning_error"}:
            params["verification_focus"] = error_type
        updated["parameters"] = params
        replanned.append(updated)
    return replanned


async def critic_node(state: dict[str, Any]) -> dict[str, Any]:
    synthesis = state.get("results", {}).get("synthesis", {})
    synthesis_claims = synthesis.get("claims", [])

    citation_index = state.get("citation_index", {})
    evidence_strength = float(state.get("evidence_strength", 0.0))

    # Claim verification
    verification = verify_claims(synthesis_claims, citation_index, evidence_strength)

    hallucination_issues: list[dict[str, Any]] = []
    for claim in synthesis_claims:
        refs = claim.get("evidence_refs", [])
        if not refs and not is_data_gap_claim(claim.get("text", "")):
            claim_id = claim.get("claim_id")
            hallucination_issues.append(
                {
                    "claim_id": claim_id,
                    "issue": "missing_evidence_refs",
                }
            )

    # Conflict arbitration
    arbitration = arbitrate_conflicts(synthesis_claims)

    decision = "approve"
    force_replan = False
    replanned_tasks = []
    correction_prompt = None
    retry_counts = dict(state.get("retry_count_by_domain", {}))

    if hallucination_issues:
        decision = "retry"
        correction_prompt = (
            "Attach evidence_refs for every claim and re-run verification."
        )
        force_replan = True
    elif verification.invalid_major_claim_ids:
        decision = "retry"
        correction_prompt = (
            "Re-research the unsupported major claims and attach valid citations."
        )
        force_replan = True
    elif not arbitration.resolved:
        decision = "conflict"
    elif evidence_strength < EVIDENCE_STRENGTH_THRESHOLD:
        decision = "retry"
        correction_prompt = (
            "Evidence strength is too low. Fetch more supporting news or fundamentals."
        )
        force_replan = True

    critic_retry_count = int(retry_counts.get("critic", 0))
    if decision == "retry":
        critic_retry_count += 1
        retry_counts["critic"] = critic_retry_count

    reached_retry_limit = (
        decision == "retry" and critic_retry_count >= CRITIC_RETRY_LIMIT
    )

    if force_replan and not reached_retry_limit:
        replanned_tasks = _reprioritize_tasks(
            list(state.get("tasks", [])),
            (
                "hallucination"
                if verification.invalid_major_claim_ids
                else "incomplete_response"
            ),
            correction_prompt,
        )

    payload: dict[str, Any] = {
        "critic_decision": decision,
        "retry_count_by_domain": retry_counts,
        "hallucination_issues": hallucination_issues,
        "claim_verification": {
            "verified_claim_ids": verification.verified_claim_ids,
            "invalid_major_claim_ids": verification.invalid_major_claim_ids,
            "details": verification.verification_details,
        },
        "conflict_record": {
            "resolved": arbitration.resolved,
            "method": arbitration.method,
            "winning_claim_ids": arbitration.winning_claim_ids,
            "unresolved_claim_pairs": arbitration.unresolved_claim_pairs,
        },
        "force_replan": force_replan and not reached_retry_limit,
        "replanned_tasks": replanned_tasks,
        "task_contexts": {},
        "correction_prompt": correction_prompt,
        "confidence_score": float(state.get("confidence_score", 0.8)),
        "status": "success",
        "reasoning": f"Critic decision: {decision}. Checked {len(synthesis_claims)} claims.",
        "next_action": (
            "terminate_low_confidence"
            if reached_retry_limit
            else (
                "run_validation"
                if decision == "approve"
                else (
                    "run_conflict_resolution"
                    if decision == "conflict"
                    else "run_research_plan"
                )
            )
        ),
        "data": {"critic_decision": decision},
        "errors": [],
    }

    audit = build_node_audit_entry("critic_node", state, payload)
    audit["decision_summary"] = {
        "critic_decision": decision,
        "critic_retry_count": critic_retry_count,
        "critic_retry_limit_reached": reached_retry_limit,
        "verified_claim_count": len(verification.verified_claim_ids),
        "invalid_major_claim_ids": verification.invalid_major_claim_ids,
        "conflict_resolved": arbitration.resolved,
        "force_replan": force_replan and not reached_retry_limit,
    }
    payload["data"]["audit"] = audit

    return finalize_node_output("critic_node", payload)
