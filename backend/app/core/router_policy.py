from __future__ import annotations

from typing import Any

MAX_ITERATIONS = 8
RETRY_LIMIT = 3
CONFIDENCE_THRESHOLD = 0.75
EVIDENCE_STRENGTH_THRESHOLD = 0.55
FRESHNESS_THRESHOLD = 0.6


def _needs_refetch(data_status: dict[str, Any], retry_count: dict[str, int]) -> bool:
    if retry_count.get("data_fetch", 0) >= RETRY_LIMIT:
        return False

    for dataset in ("ohlcv", "news", "fundamentals", "macro"):
        status = data_status.get(dataset, {})
        if not status.get("available", False):
            return True
        if float(status.get("freshness", 0.0)) < FRESHNESS_THRESHOLD:
            return True
    return False


def decide_next_action(state: dict[str, Any]) -> str:
    iteration_count = int(state.get("iteration_count", 0))
    if iteration_count >= MAX_ITERATIONS:
        return "terminate_budget_exceeded"

    retry_count = state.get("retry_count_by_domain", {})
    if any(count >= RETRY_LIMIT for count in retry_count.values()):
        return "terminate_budget_exceeded"

    if not state.get("goal"):
        return "run_goal_hypothesis"

    if _needs_refetch(state.get("data_status", {}), retry_count):
        return "run_data_fetch"

    if not state.get("tasks"):
        return "run_research_plan"

    critic_decision = state.get("critic_decision")
    if critic_decision == "conflict":
        return "run_conflict_resolution"

    if float(state.get("evidence_strength", 0.0)) < EVIDENCE_STRENGTH_THRESHOLD:
        return "run_reflection"

    if critic_decision == "retry":
        return "run_reflection"

    confidence_score = float(state.get("confidence_score", 0.0))
    validation_passed = bool(state.get("validation_passed", False))

    if (
        critic_decision == "approve"
        and validation_passed
        and confidence_score >= CONFIDENCE_THRESHOLD
    ):
        return "terminate_success"

    if "synthesis" not in state.get("results", {}):
        return "run_synthesis"

    if critic_decision is None:
        return "run_critic"

    if not validation_passed and critic_decision == "approve":
        return "run_validation"

    return "run_research_exec"
