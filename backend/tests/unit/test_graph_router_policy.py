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
    assert decide_next_action(state) == "run_goal"


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


def test_router_terminates_when_required_data_is_incomplete_after_fetch_budget_exhausted() -> (
    None
):
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

    assert decide_next_action(state) == "terminate_insufficient_data"


def test_router_blocks_research_when_required_dataset_coverage_is_zero() -> None:
    state = {
        "iteration_count": 2,
        "retry_count_by_domain": {"data_fetch": 3},
        "goal": {"objective": "test"},
        "timeframe_policy": {
            "ohlcv": {"minimum_coverage_ratio": 0.8},
            "news": {"minimum_coverage_ratio": 0.5},
            "fundamentals": {"minimum_coverage_ratio": 0.75},
            "macro": {"minimum_coverage_ratio": 1.0},
        },
        "data_status": {
            "ohlcv": {"available": True, "freshness": 0.95, "coverage": 1.0},
            "news": {"available": True, "freshness": 0.9, "coverage": 1.0},
            "fundamentals": {"available": True, "freshness": 1.0, "coverage": 0.0},
            "macro": {"available": True, "freshness": 1.0, "coverage": 1.0},
        },
        "tasks": [],
        "results": {},
        "critic_decision": None,
        "confidence_score": 0.3,
        "evidence_strength": 0.3,
        "validation_passed": False,
    }

    assert decide_next_action(state) == "terminate_insufficient_data"


def test_router_runs_data_fetch_when_data_ready_but_not_materialized() -> None:
    state = {
        "iteration_count": 1,
        "retry_count_by_domain": {},
        "goal": {"objective": "test", "ticker": "AAPL"},
        "timeframe_policy": {
            "ohlcv": {"minimum_coverage_ratio": 0.8},
            "news": {"minimum_coverage_ratio": 0.5},
            "fundamentals": {"minimum_coverage_ratio": 0.75},
            "macro": {"minimum_coverage_ratio": 1.0},
        },
        "data_status": {
            "ohlcv": {"available": True, "freshness": 1.0, "coverage": 1.0},
            "news": {"available": True, "freshness": 1.0, "coverage": 1.0},
            "fundamentals": {"available": True, "freshness": 1.0, "coverage": 1.0},
            "macro": {"available": True, "freshness": 1.0, "coverage": 1.0},
        },
        "fetched_data": {},
        "tasks": [],
        "results": {},
        "critic_decision": None,
        "confidence_score": 0.3,
        "evidence_strength": 0.3,
        "validation_passed": False,
    }
    assert decide_next_action(state) == "run_data_fetch"


def test_router_treats_none_synthesis_as_not_ready() -> None:
    state = {
        "iteration_count": 1,
        "retry_count_by_domain": {},
        "goal": {"objective": "test", "ticker": "AAPL"},
        "data_status": {
            "ohlcv": {"available": True, "freshness": 1.0, "coverage": 1.0},
            "news": {"available": True, "freshness": 1.0, "coverage": 1.0},
            "fundamentals": {"available": True, "freshness": 1.0, "coverage": 1.0},
            "macro": {"available": True, "freshness": 1.0, "coverage": 1.0},
        },
        "fetched_data": {
            "ohlcv": {"by_symbol": {"AAPL": {"data": [1]}}},
            "fundamentals": {"by_symbol": {"AAPL": {"marketCap": 1}}},
            "macro": {"NIFTY_50": 1},
            "news": [{"title": "x"}],
        },
        "tasks": [{"task_id": "fundamental_analysis"}],
        "task_contexts": {},
        "results": {"synthesis": None},
        "critic_decision": None,
        "confidence_score": 0.3,
        "evidence_strength": 0.3,
        "validation_passed": False,
    }

    assert decide_next_action(state) == "run_research_context"


def test_router_relies_on_critic_owned_retries_under_low_evidence() -> None:
    state = {
        "iteration_count": 6,
        "retry_count_by_domain": {"critic": 2},
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

    assert decide_next_action(state) == "run_research_plan"


def test_router_terminates_low_confidence_when_critic_retry_limit_is_hit() -> None:
    state = {
        "iteration_count": 4,
        "retry_count_by_domain": {"critic": 3},
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
        "evidence_strength": 0.2,
        "validation_passed": False,
    }

    assert decide_next_action(state) == "terminate_low_confidence"


def test_router_terminates_low_confidence_for_repeated_research_plan_loop() -> None:
    state = {
        "iteration_count": 8,
        "retry_count_by_domain": {},
        "goal": {"objective": "test"},
        "data_status": {
            "ohlcv": {"available": True, "freshness": 1.0, "coverage": 1.0},
            "news": {"available": True, "freshness": 1.0, "coverage": 1.0},
            "fundamentals": {"available": True, "freshness": 1.0, "coverage": 1.0},
            "macro": {"available": True, "freshness": 1.0, "coverage": 1.0},
        },
        "tasks": [{"task_id": "t1"}],
        "task_contexts": {"t1": {"summary": "ready"}},
        "fetched_data": {
            "ohlcv": {"by_symbol": {"AAPL": {"data": [{"Date": "2026-04-09"}]}}},
            "fundamentals": {"by_symbol": {"AAPL": {"marketCap": 10}}},
            "news": [{"title": "x", "summary": "y", "content": "z"}],
            "macro": {"NIFTY_50": 22000.0},
        },
        "results": {"synthesis": {"decision": "watchlist"}},
        "critic_decision": "retry",
        "confidence_score": 0.5,
        "evidence_strength": 0.2,
        "validation_passed": False,
        "consecutive_research_plan_routes": 3,
    }

    assert decide_next_action(state) == "terminate_low_confidence"


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
        "approved_agents": [
            "fundamental_analysis",
            "technical_analysis",
            "sentiment_analysis",
            "macro_analysis",
            "contrarian_analysis",
        ],
        "tasks": [{"task_id": "t1"}],
        "results": {
            "fundamental_analysis": {"analysis": "cached"},
            "technical_analysis": {"analysis": "cached"},
            "sentiment_analysis": {"analysis": "cached"},
            "macro_analysis": {"analysis": "cached"},
            "contrarian_analysis": {"analysis": "cached"},
        },
        "critic_decision": None,
        "confidence_score": 0.55,
        "evidence_strength": 0.6,
        "validation_passed": False,
    }

    assert decide_next_action(state) == "run_synthesis"


def test_router_suspends_when_plan_waits_for_user_input() -> None:
    state = {
        "iteration_count": 1,
        "retry_count_by_domain": {},
        "goal": {"objective": "test"},
        "plan_status": "awaiting_approval",
        "data_status": {},
        "tasks": [],
        "results": {},
        "critic_decision": None,
        "confidence_score": 0.0,
        "evidence_strength": 0.0,
        "validation_passed": False,
    }

    assert decide_next_action(state) == "terminate_awaiting_input"


def test_router_requires_evaluator_pass_before_terminating_success() -> None:
    state = {
        "iteration_count": 2,
        "retry_count_by_domain": {},
        "goal": {"objective": "test"},
        "data_status": {
            "ohlcv": {"available": True, "freshness": 0.9},
            "news": {"available": True, "freshness": 0.9},
            "fundamentals": {"available": True, "freshness": 0.9},
            "macro": {"available": True, "freshness": 0.9},
        },
        "tasks": [{"task_id": "t1"}],
        "results": {"synthesis": {"decision": "watchlist"}},
        "critic_decision": "approve",
        "confidence_score": 0.85,
        "evidence_strength": 0.8,
        "validation_passed": True,
        "evaluation_passed": False,
        "evaluation_result": {"score": 0.5, "error_type": "reasoning_error"},
    }

    assert decide_next_action(state) == "run_research_plan"


def test_router_honors_critic_terminal_failure() -> None:
    state = {
        "iteration_count": 2,
        "retry_count_by_domain": {"critic": 3},
        "goal": {"objective": "test"},
        "data_status": {
            "ohlcv": {"available": True, "freshness": 0.9},
            "news": {"available": True, "freshness": 0.9},
            "fundamentals": {"available": True, "freshness": 0.9},
            "macro": {"available": True, "freshness": 0.9},
        },
        "tasks": [{"task_id": "t1"}],
        "results": {"synthesis": {"decision": "watchlist"}},
        "critic_decision": "terminate_failure",
        "confidence_score": 0.2,
        "evidence_strength": 0.2,
        "validation_passed": False,
    }

    assert decide_next_action(state) == "terminate_failure"


def test_router_prefers_progress_when_retry_limit_is_hit_but_research_can_still_advance() -> (
    None
):
    state = {
        "iteration_count": 2,
        "retry_count_by_domain": {"critic": 3},
        "goal": {"objective": "test"},
        "data_status": {
            "ohlcv": {"available": True, "freshness": 0.9},
            "news": {"available": True, "freshness": 0.9},
            "fundamentals": {"available": True, "freshness": 0.9},
            "macro": {"available": True, "freshness": 0.9},
        },
        "tasks": [{"task_id": "t1"}],
        "results": {},
        "critic_decision": None,
        "confidence_score": 0.2,
        "evidence_strength": 0.2,
        "validation_passed": False,
    }

    assert decide_next_action(state) == "run_data_fetch"


def test_router_runs_execution_after_task_contexts_are_ready() -> None:
    state = {
        "iteration_count": 2,
        "retry_count_by_domain": {},
        "goal": {"objective": "test"},
        "data_status": {
            "ohlcv": {"available": True, "freshness": 0.9, "coverage": 1.0},
            "news": {"available": True, "freshness": 0.9, "coverage": 1.0},
            "fundamentals": {"available": True, "freshness": 0.9, "coverage": 1.0},
            "macro": {"available": True, "freshness": 0.9, "coverage": 1.0},
        },
        "tasks": [{"task_id": "t1"}],
        "task_contexts": {"t1": {"agent": "fundamental_analysis"}},
        "fetched_data": {
            "ohlcv": {"by_symbol": {"AAPL": {"data": [{"Date": "2026-04-09"}]}}},
            "fundamentals": {"by_symbol": {"AAPL": {"marketCap": 10}}},
            "news": [{"title": "x", "summary": "y", "content": "z"}],
            "macro": {"NIFTY_50": 22000.0},
        },
        "results": {},
        "critic_decision": None,
        "confidence_score": 0.5,
        "evidence_strength": 0.5,
        "validation_passed": False,
    }

    assert decide_next_action(state) == "run_research_execution"
