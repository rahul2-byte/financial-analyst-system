import pytest

from app.core.graph.nodes.autonomous_quality_nodes import autonomous_reflection_node
from app.core.graph.router_policy import decide_next_action


@pytest.mark.asyncio
async def test_reflection_resets_critic_state_and_requests_replan() -> None:
    state = {
        "retry_count_by_domain": {"research": 1},
        "tasks": [
            {"task_id": "fundamental_analysis", "priority": "P1"},
            {"task_id": "sentiment_analysis", "priority": "P1"},
        ],
        "results": {"synthesis": {"decision": "no_call"}},
        "critic_decision": "retry",
        "confidence_score": 0.42,
        "evidence_strength": 0.31,
    }

    result = await autonomous_reflection_node(state)

    assert result["retry_count_by_domain"]["research"] == 2
    assert result["critic_decision"] is None
    assert result["force_replan"] is True
    assert result["tasks"] == []


def test_router_honors_reflection_replan_flag_before_low_evidence_loop() -> None:
    state = {
        "iteration_count": 2,
        "retry_count_by_domain": {"research": 1},
        "goal": {"objective": "test"},
        "force_replan": True,
        "data_status": {
            "ohlcv": {"available": True, "freshness": 0.9},
            "news": {"available": True, "freshness": 0.9},
            "fundamentals": {"available": True, "freshness": 0.9},
            "macro": {"available": True, "freshness": 0.9},
        },
        "tasks": [{"task_id": "stale_task"}],
        "results": {"synthesis": {"decision": "watchlist"}},
        "critic_decision": "retry",
        "confidence_score": 0.3,
        "evidence_strength": 0.2,
        "validation_passed": False,
    }

    assert decide_next_action(state) == "run_research_plan"
