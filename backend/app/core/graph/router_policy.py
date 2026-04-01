from __future__ import annotations

from typing import Any

MAX_ITERATIONS = 8
RETRY_LIMIT = 3
CONFIDENCE_THRESHOLD = 0.75
EVIDENCE_STRENGTH_THRESHOLD = 0.55
FRESHNESS_THRESHOLD = 0.6


def _required_data_ready(data_status: dict[str, Any]) -> bool:
    required = ("ohlcv", "news", "fundamentals", "macro")
    for dataset in required:
        status = data_status.get(dataset, {})
        if not status.get("available", False):
            return False
        if float(status.get("freshness", 0.0)) < FRESHNESS_THRESHOLD:
            return False
    return True


def _available_dataset_count(data_status: dict[str, Any]) -> int:
    required = ("ohlcv", "news", "fundamentals", "macro")
    return sum(1 for dataset in required if data_status.get(dataset, {}).get("available", False))


def _can_retry_fetch(retries: dict[str, int]) -> bool:
    return retries.get("data_fetch", 0) < RETRY_LIMIT


def _is_confidence_stagnating(confidence_history: list[float], tolerance: float = 0.01) -> bool:
    if len(confidence_history) < 3:
        return False
    sample = confidence_history[-3:]
    return max(sample) - min(sample) <= tolerance


def _has_cached_research_results(results: dict[str, Any]) -> bool:
    required = ("fundamental_analysis", "sentiment_analysis", "macro_analysis")
    return all(results.get(key) for key in required)


def decide_next_action(state: dict[str, Any]) -> str:
    iteration_count = int(state.get("iteration_count", 0))
    if iteration_count >= MAX_ITERATIONS:
        return "terminate_budget_exceeded"

    retry_counts = state.get("retry_count_by_domain", {})
    non_fetch_retries = [
        count for domain, count in retry_counts.items() if domain != "data_fetch"
    ]
    if any(count >= RETRY_LIMIT for count in non_fetch_retries):
        return "terminate_budget_exceeded"

    remaining_budget = float(state.get("execution_budget", {}).get("remaining", 1.0))
    if remaining_budget <= 0.0:
        return "terminate_budget_exceeded"

    if not state.get("goal"):
        return "run_goal_hypothesis"

    data_status = state.get("data_status", {})
    if not _required_data_ready(data_status):
        if _can_retry_fetch(retry_counts):
            return "run_data_check"
        if _available_dataset_count(data_status) > 0:
            if not state.get("tasks"):
                return "run_research_plan"
            return "run_research_exec"
        return "terminate_insufficient_data"

    if bool(state.get("force_replan", False)):
        return "run_research_plan"

    if (
        int(state.get("iteration_count", 0)) >= 4
        and _is_confidence_stagnating(list(state.get("confidence_history", [])))
        and float(state.get("evidence_strength", 0.0)) < EVIDENCE_STRENGTH_THRESHOLD
    ):
        return "terminate_insufficient_data"

    if not state.get("tasks"):
        return "run_research_plan"

    critic_decision = state.get("critic_decision")
    if critic_decision == "conflict":
        return "run_conflict_resolution"

    evidence_strength = float(state.get("evidence_strength", 0.0))
    if evidence_strength < EVIDENCE_STRENGTH_THRESHOLD:
        if retry_counts.get("research", 0) < RETRY_LIMIT:
            return "run_reflection"
        return "terminate_insufficient_data"

    results = state.get("results", {})
    if "synthesis" not in results and _has_cached_research_results(results):
        return "run_synthesis"

    if "synthesis" not in results:
        return "run_research_exec"

    if critic_decision is None:
        return "run_critic"

    if critic_decision == "retry":
        if retry_counts.get("research", 0) < RETRY_LIMIT:
            return "run_reflection"
        return "terminate_insufficient_data"

    if critic_decision == "approve" and not bool(state.get("validation_passed", False)):
        return "run_validation"

    confidence_score = float(state.get("confidence_score", 0.0))
    if (
        critic_decision == "approve"
        and bool(state.get("validation_passed", False))
        and confidence_score >= CONFIDENCE_THRESHOLD
    ):
        return "terminate_success"

    return "run_research_exec"
