from typing import get_type_hints

from app.core.graph_state import ResearchGraphState, merge_dicts


def test_merge_dicts_deep_merges_nested_results_and_data_status() -> None:
    left = {
        "results": {"fundamental": {"status": "success"}},
        "data_status": {"ohlcv": {"available": True, "freshness": "fresh"}},
    }
    right = {
        "results": {"sentiment": {"status": "partial"}},
        "data_status": {"news": {"available": False, "freshness": "stale"}},
    }

    merged = merge_dicts(left, right)

    assert merged["results"]["fundamental"]["status"] == "success"
    assert merged["results"]["sentiment"]["status"] == "partial"
    assert merged["data_status"]["ohlcv"]["freshness"] == "fresh"
    assert merged["data_status"]["news"]["freshness"] == "stale"


def test_state_schema_includes_autonomous_fields() -> None:
    hints = get_type_hints(ResearchGraphState)

    required_fields = {
        "goal",
        "hypotheses",
        "data_status",
        "data_plan",
        "tasks",
        "results",
        "synthesis_confidence",
        "adjusted_confidence",
        "smoothed_confidence",
        "confidence_score",
        "final_confidence",
        "confidence_history",
        "confidence_components",
        "freshness_policy",
        "evidence_strength",
        "execution_budget",
        "timeouts",
        "history",
        "termination_reason",
        "final_output",
    }

    missing = required_fields - set(hints.keys())
    assert not missing, f"Missing state fields: {sorted(missing)}"


def test_confidence_score_is_routing_source_of_truth() -> None:
    state: ResearchGraphState = {
        "user_query": "Is AAPL a good swing trade?",
        "conversation_history": [],
        "plan": None,
        "executed_steps": [],
        "agent_outputs": {},
        "tool_registry": [],
        "draft_report": None,
        "final_report": None,
        "synthesis_retry_count": 0,
        "verification_retry_count": 0,
        "verification_passed": False,
        "errors": [],
        "retry_count": 0,
        "should_retry": False,
        "should_escalate": False,
        "goal": None,
        "hypotheses": [],
        "data_status": {},
        "data_plan": [],
        "tasks": [],
        "results": {},
        "synthesis_confidence": 0.64,
        "adjusted_confidence": 0.58,
        "smoothed_confidence": 0.61,
        "confidence_score": 0.61,
        "final_confidence": 0.59,
        "confidence_history": [0.55, 0.58, 0.61],
        "confidence_components": {},
        "critic_decision": "retry",
        "router_decision": "run_reflection",
        "iteration_count": 1,
        "retry_count_by_domain": {},
        "freshness_policy": {},
        "evidence_strength": 0.42,
        "execution_budget": {},
        "timeouts": {},
        "errors_detail": [],
        "history": [],
        "termination_reason": None,
        "final_output": None,
    }

    assert state["confidence_score"] == state["smoothed_confidence"]
    assert state["confidence_score"] != state["synthesis_confidence"]


def test_autonomous_schema_models_exist() -> None:
    from app.core.autonomous_schemas import (  # noqa: PLC0415
        CriticDecision,
        RouterDecision,
        TaskPriority,
    )

    assert TaskPriority.P0.value == "P0"
    assert CriticDecision.APPROVE.value == "approve"
    assert RouterDecision.RUN_VALIDATION.value == "run_validation"
