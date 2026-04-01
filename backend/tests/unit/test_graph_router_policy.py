from app.core.graph.router_policy import decide_next_action


def test_router_transitions_to_goal_when_goal_missing() -> None:
    state = {
        "iteration_count": 0,
        "retry_count_by_domain": {},
        "goal": None,
        "data_status": {},
        "tasks": [],
        "results": {},
        "critic_decision": None,
        "confidence_score": 0.0,
        "evidence_strength": 0.0,
        "validation_passed": False,
    }
    assert decide_next_action(state) == "run_goal_hypothesis"


def test_router_transitions_to_validation_for_approved_high_confidence() -> None:
    state = {
        "iteration_count": 1,
        "retry_count_by_domain": {},
        "goal": {"objective": "test"},
        "data_status": {
            "ohlcv": {"available": True, "freshness": 1.0},
            "news": {"available": True, "freshness": 1.0},
            "fundamentals": {"available": True, "freshness": 1.0},
            "macro": {"available": True, "freshness": 1.0},
        },
        "tasks": [{"task_id": "t1"}],
        "results": {"synthesis": {"decision": "hold"}},
        "critic_decision": "approve",
        "confidence_score": 0.8,
        "evidence_strength": 0.7,
        "validation_passed": False,
    }
    assert decide_next_action(state) == "run_validation"


def test_router_allows_partial_data_progression_after_fetch_budget_exhausted() -> None:
    state = {
        "iteration_count": 4,
        "retry_count_by_domain": {"data_fetch": 3},
        "goal": {"objective": "test"},
        "data_status": {
            "ohlcv": {"available": True, "freshness": 0.9},
            "news": {"available": False, "freshness": 0.0},
            "fundamentals": {"available": False, "freshness": 0.0},
            "macro": {"available": False, "freshness": 0.0},
        },
        "tasks": [],
        "results": {},
        "critic_decision": None,
        "confidence_score": 0.3,
        "evidence_strength": 0.3,
        "validation_passed": False,
    }

    assert decide_next_action(state) == "run_research_plan"


def test_router_terminates_when_confidence_stagnates_under_low_evidence() -> None:
    state = {
        "iteration_count": 6,
        "retry_count_by_domain": {"research": 2},
        "goal": {"objective": "test"},
        "data_status": {
            "ohlcv": {"available": True, "freshness": 0.9},
            "news": {"available": True, "freshness": 0.9},
            "fundamentals": {"available": True, "freshness": 0.9},
            "macro": {"available": True, "freshness": 0.9},
        },
        "tasks": [{"task_id": "t1"}],
        "results": {"synthesis": {"decision": "watchlist"}},
        "critic_decision": "retry",
        "confidence_score": 0.41,
        "confidence_history": [0.409, 0.41, 0.411],
        "evidence_strength": 0.35,
        "validation_passed": False,
    }

    assert decide_next_action(state) == "terminate_insufficient_data"


def test_router_terminates_when_execution_budget_exhausted() -> None:
    state = {
        "iteration_count": 2,
        "retry_count_by_domain": {},
        "goal": {"objective": "test"},
        "execution_budget": {"remaining": 0.0},
        "data_status": {
            "ohlcv": {"available": True, "freshness": 0.9},
            "news": {"available": True, "freshness": 0.9},
            "fundamentals": {"available": True, "freshness": 0.9},
            "macro": {"available": True, "freshness": 0.9},
        },
        "tasks": [{"task_id": "t1"}],
        "results": {},
        "critic_decision": None,
        "confidence_score": 0.5,
        "evidence_strength": 0.5,
        "validation_passed": False,
    }

    assert decide_next_action(state) == "terminate_budget_exceeded"


def test_router_reuses_cached_research_results_before_reexecution() -> None:
    state = {
        "iteration_count": 3,
        "retry_count_by_domain": {},
        "goal": {"objective": "test"},
        "data_status": {
            "ohlcv": {"available": True, "freshness": 0.9},
            "news": {"available": True, "freshness": 0.9},
            "fundamentals": {"available": True, "freshness": 0.9},
            "macro": {"available": True, "freshness": 0.9},
        },
        "tasks": [{"task_id": "t1"}],
        "results": {
            "fundamental_analysis": {"analysis": "cached"},
            "sentiment_analysis": {"analysis": "cached"},
            "macro_analysis": {"analysis": "cached"},
        },
        "critic_decision": None,
        "confidence_score": 0.55,
        "evidence_strength": 0.6,
        "validation_passed": False,
    }

    assert decide_next_action(state) == "run_synthesis"
