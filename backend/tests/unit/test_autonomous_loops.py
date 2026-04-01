import pytest
import asyncio

from app.core.async_control import run_parallel_with_timeout
from app.core.nodes.data_checker_node import data_checker_node
from app.core.nodes.data_fetch_node import data_fetch_node
from app.core.nodes.data_planner_node import data_planner_node
from app.core.nodes.goal_hypothesis_node import goal_hypothesis_node


@pytest.mark.asyncio
async def test_goal_hypothesis_node_returns_structured_goal_and_hypotheses() -> None:
    result = await goal_hypothesis_node({"user_query": "Is AAPL a good trade?"})

    assert result["status"] == "success"
    assert isinstance(result["data"]["goal"], dict)
    assert isinstance(result["data"]["hypotheses"], list)
    assert "reasoning" in result
    assert "confidence_score" in result
    assert "next_action" in result


@pytest.mark.asyncio
async def test_data_checker_marks_missing_and_stale_data() -> None:
    state = {
        "data_status": {
            "ohlcv": {"available": True, "freshness": 0.95},
            "news": {"available": False, "freshness": 0.0},
            "fundamentals": {"available": True, "freshness": 0.45},
            "macro": {"available": True, "freshness": 0.85},
        }
    }

    result = await data_checker_node(state)

    assert result["status"] == "partial"
    assert result["data"]["missing_datasets"] == ["news"]
    assert "fundamentals" in result["data"]["stale_datasets"]


@pytest.mark.asyncio
async def test_data_planner_prioritizes_missing_then_stale() -> None:
    checker_output = {
        "missing_datasets": ["news"],
        "stale_datasets": ["fundamentals"],
    }

    result = await data_planner_node({"checker_output": checker_output})
    plan = result["data"]["data_plan"]

    assert plan[0]["dataset"] == "news"
    assert plan[0]["priority"] == "P0"
    assert plan[1]["dataset"] == "fundamentals"


@pytest.mark.asyncio
async def test_data_fetch_only_updates_planned_datasets() -> None:
    state = {
        "data_plan": [
            {"dataset": "news", "priority": "P0"},
            {"dataset": "fundamentals", "priority": "P1"},
        ]
    }

    result = await data_fetch_node(state)

    updated = result["data"]["data_status"]
    assert updated["news"]["available"] is True
    assert updated["fundamentals"]["available"] is True
    assert result["status"] in {"success", "partial"}


@pytest.mark.asyncio
async def test_parallel_timeout_cancels_pending_tasks() -> None:
    async def fast() -> str:
        return "ok"

    async def slow() -> str:
        await asyncio.sleep(0.2)
        return "late"

    completed, errors = await run_parallel_with_timeout(
        [fast(), slow()], task_timeout_s=0.05, stage_timeout_s=0.1
    )

    assert "ok" in completed
    assert any("timeout" in error.lower() for error in errors)
