from app.core.router_policy import (
    CONFIDENCE_THRESHOLD,
    EVIDENCE_STRENGTH_THRESHOLD,
    MAX_ITERATIONS,
    RETRY_LIMIT,
    decide_next_action,
)


def _base_state() -> dict:
    return {
        "goal": {"objective": "trade analysis"},
        "data_status": {
            "ohlcv": {"available": True, "freshness": 0.95},
            "news": {"available": True, "freshness": 0.95},
            "fundamentals": {"available": True, "freshness": 0.95},
            "macro": {"available": True, "freshness": 0.95},
        },
        "tasks": [{"task_id": "t1"}],
        "results": {"synthesis": {"status": "success"}},
        "critic_decision": "approve",
        "confidence_score": CONFIDENCE_THRESHOLD + 0.05,
        "evidence_strength": EVIDENCE_STRENGTH_THRESHOLD + 0.1,
        "iteration_count": 1,
        "retry_count_by_domain": {"data_fetch": 0, "research": 0},
        "validation_passed": True,
    }


def test_router_prioritizes_conflict_path() -> None:
    state = _base_state()
    state["critic_decision"] = "conflict"

    assert decide_next_action(state) == "run_conflict_resolution"


def test_router_refetches_when_required_dataset_stale() -> None:
    state = _base_state()
    state["data_status"]["news"] = {"available": True, "freshness": 0.25}

    assert decide_next_action(state) == "run_data_fetch"


def test_router_forces_retry_on_low_evidence() -> None:
    state = _base_state()
    state["evidence_strength"] = EVIDENCE_STRENGTH_THRESHOLD - 0.01

    assert decide_next_action(state) == "run_reflection"


def test_router_uses_confidence_score_not_synthesis_confidence() -> None:
    state = _base_state()
    state["synthesis_confidence"] = 0.99
    state["confidence_score"] = CONFIDENCE_THRESHOLD - 0.01
    state["critic_decision"] = "approve"
    state["validation_passed"] = True

    assert decide_next_action(state) != "terminate_success"


def test_router_terminates_on_iteration_budget() -> None:
    state = _base_state()
    state["iteration_count"] = MAX_ITERATIONS

    assert decide_next_action(state) == "terminate_budget_exceeded"


def test_router_terminates_when_retry_limit_exhausted() -> None:
    state = _base_state()
    state["critic_decision"] = "retry"
    state["retry_count_by_domain"] = {"research": RETRY_LIMIT}

    assert decide_next_action(state) == "terminate_budget_exceeded"
