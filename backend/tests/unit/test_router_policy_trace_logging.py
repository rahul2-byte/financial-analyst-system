from __future__ import annotations

from app.core.graph.router_policy import build_router_decision_snapshot


def test_router_decision_snapshot_contains_core_predicates() -> None:
    snapshot = build_router_decision_snapshot(
        {
            "iteration_count": 2,
            "plan_status": None,
            "goal": {"ticker": "AAPL"},
            "force_replan": False,
            "data_status": {
                "ohlcv": {"available": True, "freshness": 1.0, "coverage": 1.0},
                "news": {"available": False, "freshness": 0.0, "coverage": 0.0},
                "fundamentals": {"available": True, "freshness": 1.0, "coverage": 1.0},
                "macro": {"available": True, "freshness": 1.0, "coverage": 1.0},
            },
            "timeframe_policy": {},
            "retry_count_by_domain": {"data_fetch": 1},
            "tasks": [{"task_id": "fundamental_analysis"}],
            "task_contexts": {},
            "results": {},
            "critic_decision": None,
            "validation_passed": False,
            "evaluation_passed": False,
            "evidence_strength": 0.1,
            "confidence_score": 0.2,
            "confidence_history": [0.2, 0.2, 0.2],
        }
    )

    assert snapshot["iteration_count"] == 2
    assert snapshot["goal_present"] is True
    assert snapshot["required_data_ready"] is False
    assert snapshot["required_payloads_materialized"] is False
    assert snapshot["task_contexts_ready"] is False
    assert snapshot["confidence_stagnating"] is True
