from __future__ import annotations

from typing import Any

MAX_ITERATIONS = 16
RETRY_LIMIT = 3
CONFIDENCE_THRESHOLD = 0.75
EVIDENCE_STRENGTH_THRESHOLD = 0.55
FRESHNESS_THRESHOLD = 0.6
EVALUATION_THRESHOLD = 0.8


def _dataset_ready(
    dataset: str, status: dict[str, Any], timeframe_policy: dict[str, Any]
) -> bool:
    if not status.get("available", False):
        return False
    if float(status.get("freshness", 0.0)) < FRESHNESS_THRESHOLD:
        return False
    minimum_coverage = float(
        timeframe_policy.get(dataset, {}).get("minimum_coverage_ratio", 0.0)
    )
    return float(status.get("coverage", 0.0)) >= minimum_coverage


def _required_data_ready(
    data_status: dict[str, Any], timeframe_policy: dict[str, Any]
) -> bool:
    required = ("ohlcv", "news", "fundamentals", "macro")
    for dataset in required:
        status = data_status.get(dataset, {})
        if not _dataset_ready(dataset, status, timeframe_policy):
            return False
    return True


def _available_dataset_count(data_status: dict[str, Any]) -> int:
    required = ("ohlcv", "news", "fundamentals", "macro")
    return sum(
        1
        for dataset in required
        if data_status.get(dataset, {}).get("available", False)
    )


def _can_retry_fetch(retries: dict[str, int]) -> bool:
    return retries.get("data_fetch", 0) < RETRY_LIMIT


def _is_confidence_stagnating(
    confidence_history: list[float], tolerance: float = 0.01
) -> bool:
    if len(confidence_history) < 3:
        return False
    sample = confidence_history[-3:]
    return max(sample) - min(sample) <= tolerance


def _has_cached_research_results(state: dict[str, Any]) -> bool:
    results = state.get("results", {})
    selected = state.get("approved_agents", [])
    if not selected:
        return False
    return all(results.get(agent) for agent in selected)


def _best_effort_progress_action(state: dict[str, Any]) -> str:
    results = state.get("results", {})
    critic_decision = state.get("critic_decision")

    if critic_decision == "terminate_failure":
        return "terminate_failure"
    if critic_decision == "conflict":
        return "run_conflict_resolution"
    if critic_decision == "approve" and not bool(state.get("validation_passed", False)):
        return "run_validation"
    if "synthesis" in results:
        if critic_decision is None:
            return "run_critic"
        if critic_decision == "retry":
            return "terminate_insufficient_data"
        if critic_decision == "approve":
            return (
                "terminate_success"
                if bool(state.get("validation_passed", False))
                else "run_validation"
            )
    if _has_cached_research_results(state):
        return "run_synthesis"
    if state.get("tasks"):
        return "run_research_execution"
    if state.get("goal"):
        return "run_research_plan"
    return "terminate_budget_exceeded"


def decide_next_action(state: dict[str, Any]) -> str:
    if state.get("plan_status") in {"awaiting_clarification", "awaiting_approval"}:
        return "terminate_awaiting_input"

    iteration_count = int(state.get("iteration_count", 0))
    if iteration_count >= MAX_ITERATIONS:
        return "terminate_budget_exceeded"

    retry_counts = state.get("retry_count_by_domain", {})

    if not state.get("goal"):
        return "run_goal"

    data_status = state.get("data_status", {})
    timeframe_policy = state.get("timeframe_policy", {})
    if not _required_data_ready(data_status, timeframe_policy):
        if _can_retry_fetch(retry_counts):
            return "run_data_check"
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
    if critic_decision == "terminate_failure":
        return "terminate_failure"
    if critic_decision == "conflict":
        return "run_conflict_resolution"

    non_fetch_retries = [
        count for domain, count in retry_counts.items() if domain != "data_fetch"
    ]
    remaining_budget = float(state.get("execution_budget", {}).get("remaining", 1.0))
    if (
        any(count >= RETRY_LIMIT for count in non_fetch_retries)
        or remaining_budget <= 0.0
    ):
        return _best_effort_progress_action(state)

    results = state.get("results", {})
    if "synthesis" not in results:
        if _has_cached_research_results(state):
            return "run_synthesis"
        return "run_research_execution"

    evidence_strength = float(state.get("evidence_strength", 0.0))
    if evidence_strength < EVIDENCE_STRENGTH_THRESHOLD:
        if retry_counts.get("research", 0) < RETRY_LIMIT:
            return "run_research_plan"
        return "terminate_insufficient_data"

    if critic_decision is None:
        return "run_critic"

    if critic_decision == "retry":
        if retry_counts.get("research", 0) < RETRY_LIMIT:
            return "run_research_plan"
        return "terminate_insufficient_data"

    if critic_decision == "approve" and not bool(state.get("validation_passed", False)):
        return "run_validation"

    confidence_score = float(state.get("confidence_score", 0.0))
    if (
        critic_decision == "approve"
        and bool(state.get("validation_passed", False))
        and bool(state.get("evaluation_passed", False))
        and float(state.get("evaluation_result", {}).get("score", 0.0))
        >= EVALUATION_THRESHOLD
        and confidence_score >= CONFIDENCE_THRESHOLD
    ):
        return "terminate_success"

    if critic_decision == "approve" and bool(state.get("validation_passed", False)):
        return (
            "run_research_plan" if state.get("evaluation_result") else "run_validation"
        )

    return "run_research_execution"
