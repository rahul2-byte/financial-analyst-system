from __future__ import annotations

from typing import Any

RETRY_LIMIT = 3
CRITIC_RETRY_LIMIT = 3
RESEARCH_PLAN_LOOP_LIMIT = 3
CONFIDENCE_THRESHOLD = 0.5
EVIDENCE_STRENGTH_THRESHOLD = 0.45
FRESHNESS_THRESHOLD = 0.4
EVALUATION_THRESHOLD = 0.6


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


def _required_payloads_materialized(state: dict[str, Any]) -> bool:
    fetched = state.get("fetched_data", {})
    if not isinstance(fetched, dict):
        return False

    def _has_by_symbol_payload(value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        by_symbol = value.get("by_symbol")
        return isinstance(by_symbol, dict) and any(bool(v) for v in by_symbol.values())

    if not _has_by_symbol_payload(fetched.get("ohlcv")):
        return False
    if not _has_by_symbol_payload(fetched.get("fundamentals")):
        return False
    if not isinstance(fetched.get("macro"), dict) or not fetched.get("macro"):
        return False
    news_value = fetched.get("news")
    return isinstance(news_value, list) and bool(news_value)


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


def _has_required_research_results(state: dict[str, Any]) -> bool:
    results = state.get("results", {})
    required = set(state.get("required_agents", state.get("approved_agents", [])))
    if not required:
        return False
    return all(results.get(agent) for agent in required)


def _task_contexts_ready(state: dict[str, Any]) -> bool:
    tasks = state.get("tasks", [])
    task_contexts = state.get("task_contexts", {})
    if not tasks:
        return False
    if not isinstance(task_contexts, dict):
        return False
    return all(
        isinstance(task, dict) and str(task.get("task_id", "")) in task_contexts
        for task in tasks
    )


def _best_effort_progress_action(state: dict[str, Any]) -> str:
    results = state.get("results", {})
    has_synthesis = isinstance(results, dict) and isinstance(results.get("synthesis"), dict)
    critic_decision = state.get("critic_decision")

    if critic_decision == "terminate_failure":
        return "terminate_failure"
    if critic_decision == "conflict":
        return "run_conflict_resolution"
    if critic_decision == "approve" and not bool(state.get("validation_passed", False)):
        return "run_validation"
    if has_synthesis:
        if critic_decision is None:
            return "run_critic"
        if critic_decision == "retry":
            return "terminate_low_confidence"
        if critic_decision == "approve":
            return (
                "terminate_success"
                if bool(state.get("validation_passed", False))
                else "run_validation"
            )
    if _has_required_research_results(state):
        return "run_synthesis"
    if state.get("tasks") and not _task_contexts_ready(state):
        return "run_research_context"
    if state.get("tasks"):
        return "run_research_execution"
    if state.get("goal"):
        return "run_research_plan"
    return "terminate_failure"


def decide_next_action(state: dict[str, Any]) -> str:
    if state.get("plan_status") in {"awaiting_clarification", "awaiting_approval"}:
        return "terminate_awaiting_input"

    retry_counts = state.get("retry_count_by_domain", {})
    critic_retries = int(retry_counts.get("critic", 0))
    repeated_replans = int(state.get("consecutive_research_plan_routes", 0))

    if not state.get("goal"):
        return "run_goal"

    data_status = state.get("data_status", {})
    timeframe_policy = state.get("timeframe_policy", {})
    if not _required_data_ready(data_status, timeframe_policy):
        if _can_retry_fetch(retry_counts):
            return "run_data_check"
        return "terminate_insufficient_data"

    results = state.get("results", {})
    has_synthesis = isinstance(results, dict) and isinstance(results.get("synthesis"), dict)
    # Required datasets may be present in storage, but research execution needs the
    # payloads materialized into state["fetched_data"] first. Once synthesis is
    # already produced (or required agent results are cached), we avoid forcing
    # a fetch/materialize loop.
    if (
        isinstance(results, dict)
        and not has_synthesis
        and not _has_required_research_results(state)
        and not _required_payloads_materialized(state)
    ):
        return "run_data_fetch"

    if bool(state.get("force_replan", False)):
        return "run_research_plan"

    if not state.get("tasks"):
        return "run_research_plan"

    critic_decision = state.get("critic_decision")
    if critic_decision == "terminate_failure":
        return "terminate_failure"
    if critic_decision == "conflict":
        return "run_conflict_resolution"
    if critic_decision == "retry":
        if critic_retries >= CRITIC_RETRY_LIMIT:
            return "terminate_low_confidence"
        if repeated_replans >= RESEARCH_PLAN_LOOP_LIMIT:
            return "terminate_low_confidence"
        return "run_research_plan"

    non_fetch_retries = [
        count for domain, count in retry_counts.items() if domain != "data_fetch"
    ]
    if any(count >= RETRY_LIMIT for count in non_fetch_retries):
        return _best_effort_progress_action(state)

    if not has_synthesis:
        if _has_required_research_results(state):
            return "run_synthesis"
        if not _task_contexts_ready(state):
            return "run_research_context"
        return "run_research_execution"

    if critic_decision is None:
        return "run_critic"

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


def build_router_decision_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    data_status = state.get("data_status", {})
    timeframe_policy = state.get("timeframe_policy", {})
    retry_counts = state.get("retry_count_by_domain", {})
    confidence_history = list(state.get("confidence_history", []))
    available_count = (
        _available_dataset_count(data_status) if isinstance(data_status, dict) else 0
    )

    return {
        "iteration_count": int(state.get("iteration_count", 0) or 0),
        "consecutive_research_plan_routes": int(
            state.get("consecutive_research_plan_routes", 0) or 0
        ),
        "plan_status": state.get("plan_status"),
        "goal_present": bool(state.get("goal")),
        "force_replan": bool(state.get("force_replan", False)),
        "required_data_ready": (
            _required_data_ready(data_status, timeframe_policy)
            if isinstance(data_status, dict) and isinstance(timeframe_policy, dict)
            else False
        ),
        "required_payloads_materialized": _required_payloads_materialized(state),
        "available_dataset_count": available_count,
        "task_contexts_ready": _task_contexts_ready(state),
        "required_research_results_ready": _has_required_research_results(state),
        "critic_decision": state.get("critic_decision"),
        "validation_passed": bool(state.get("validation_passed", False)),
        "evaluation_passed": bool(state.get("evaluation_passed", False)),
        "evidence_strength": float(state.get("evidence_strength", 0.0) or 0.0),
        "confidence_score": float(state.get("confidence_score", 0.0) or 0.0),
        "confidence_stagnating": _is_confidence_stagnating(confidence_history),
        "retry_count_by_domain": (
            {str(k): int(v) for k, v in retry_counts.items()}
            if isinstance(retry_counts, dict)
            else {}
        ),
        "critic_retry_limit": CRITIC_RETRY_LIMIT,
        "research_plan_loop_limit": RESEARCH_PLAN_LOOP_LIMIT,
    }
