from __future__ import annotations

from typing import Any

from app.core.contracts.graph_node import finalize_node_output
from app.core.intelligence import (
    EvaluationFeedback,
    IntelligenceAction,
    SystemIntelligenceLayer,
)
from app.core.node_resources import resources
from agents.quality.evidence import (
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


def _memory_store():
    existing = getattr(resources, "_sql_db", None)
    if existing is not None:
        return existing
    try:
        return resources.sql_db
    except Exception:  # noqa: BLE001
        return None


def _retry_feedback(
    decision: str,
    hallucination_issues: list[dict[str, Any]],
    contradiction_records: list[dict[str, Any]],
    evidence_strength: float,
) -> tuple[str, str]:
    if hallucination_issues:
        return (
            "hallucination",
            "Critic detected unsupported claims that were not grounded in evidence.",
        )
    if any(record.get("type") != "evidence_gap" for record in contradiction_records):
        return "reasoning_error", "Critic detected contradictions across agent outputs."
    if decision == "retry" and evidence_strength < EVIDENCE_STRENGTH_THRESHOLD:
        return (
            "incomplete_response",
            "Evidence strength is too low to support a reliable thesis.",
        )
    return (
        "reasoning_error",
        "Critic requested another iteration to improve the response.",
    )


async def critic_node(state: dict[str, Any]) -> dict[str, Any]:
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
            "direction": signal_from_text(
                state.get("results", {}).get("fundamental_analysis", "")
            ),
            "horizon": horizon_from_text(
                state.get("results", {}).get("fundamental_analysis", "")
            ),
            "intensity": intensity_from_text(
                state.get("results", {}).get("fundamental_analysis", "")
            ),
            "evidence_count": evidence_counts.get("fundamental_analysis", 0),
        },
        {
            "agent": "sentiment_analysis",
            "direction": signal_from_text(
                state.get("results", {}).get("sentiment_analysis", "")
            ),
            "horizon": horizon_from_text(
                state.get("results", {}).get("sentiment_analysis", "")
            ),
            "intensity": intensity_from_text(
                state.get("results", {}).get("sentiment_analysis", "")
            ),
            "evidence_count": evidence_counts.get("sentiment_analysis", 0),
        },
        {
            "agent": "macro_analysis",
            "direction": signal_from_text(
                state.get("results", {}).get("macro_analysis", "")
            ),
            "horizon": horizon_from_text(
                state.get("results", {}).get("macro_analysis", "")
            ),
            "intensity": intensity_from_text(
                state.get("results", {}).get("macro_analysis", "")
            ),
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
        synthesis_confidence
        - freshness_penalty
        - contradiction_penalty
        - hallucination_penalty,
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

    retry_counts = dict(state.get("retry_count_by_domain", {}))
    force_replan = False
    replanned_tasks: list[dict[str, Any]] = []
    correction_prompt: str | None = None
    intelligence_decision: dict[str, Any] = {}

    if decision == "retry":
        error_type, feedback = _retry_feedback(
            decision, hallucination_issues, contradiction_records, evidence_strength
        )
        sil = SystemIntelligenceLayer(
            memory_store=_memory_store(),
            max_retries=3,
            pass_threshold=0.8,
        )
        sil_decision = sil.process_evaluation(
            query_id=str(
                state.get("query_id")
                or state.get("goal", {}).get("ticker")
                or state.get("user_query", "unknown")
            ),
            user_input=str(state.get("user_query", "")),
            candidate_output=str(synthesis),
            evaluation=EvaluationFeedback(
                score=adjusted_confidence,
                error_type=error_type,
                feedback=feedback,
            ),
            current_retries=int(retry_counts.get("research", 0)),
            agent_name="critic",
        )
        retry_counts["research"] = sil_decision.retry_count
        correction_prompt = sil_decision.correction_prompt
        intelligence_decision = sil.as_payload(sil_decision)
        if sil_decision.action == IntelligenceAction.RETRY:
            force_replan = True
            replanned_tasks = _reprioritize_tasks(
                list(state.get("tasks", [])),
                sil_decision.error_type,
                sil_decision.correction_prompt,
            )
        else:
            decision = "terminate_failure"

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
        "retry_count_by_domain": retry_counts,
        "force_replan": force_replan,
        "replanned_tasks": replanned_tasks,
        "correction_prompt": correction_prompt,
        "intelligence_decision": intelligence_decision,
        "status": "success",
        "reasoning": "Applied evidence and consistency checks to synthesized output.",
        "next_action": (
            "run_validation"
            if decision == "approve"
            else (
                "terminate_failure"
                if decision == "terminate_failure"
                else "run_research_plan"
            )
        ),
        "data": {"critic_decision": decision},
        "errors": [],
    }
    return finalize_node_output("critic_node", payload)
