import pytest

from agents.financial.research.research_plan_node import research_plan_node


@pytest.mark.asyncio
async def test_research_plan_node_marks_missing_evidence_dimensions_in_tasks() -> None:
    state = {
        "goal": {"ticker": "INFY", "objective": "Assess INFY earnings risk"},
        "user_query": "Assess INFY earnings risk",
        "approved_agents": ["fundamental_analysis", "sentiment_analysis"],
        "fetched_data": {
            "fundamentals": {"by_symbol": {"INFY": {"marketCap": 1}}},
            "news": {},
        },
        "data_status": {
            "fundamentals": {"available": True, "coverage": 0.2, "freshness": 0.9},
            "news": {"available": False, "coverage": 0.0, "freshness": 0.0},
        },
        "hypotheses": [
            {
                "id": "h1",
                "statement": "Earnings quality may be weakening",
                "priority": "P0",
            }
        ],
        "confidence_score": 0.6,
    }

    result = await research_plan_node(state)

    assert result["status"] == "success"
    assert result["tasks"]
    assert result["next_action"] == "run_research_context"
    assert any("missing_dimensions" in task["parameters"] for task in result["tasks"])
    assert any(task["parameters"].get("research_question") for task in result["tasks"])
    assert all(
        task["research_question"]
        != f"Analyze {task['agent'].replace('_', ' ')} for INFY"
        for task in result["tasks"]
    )
