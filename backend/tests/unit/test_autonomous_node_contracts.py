import pytest

from app.core.nodes.data_checker_node import data_checker_node
from app.core.nodes.data_fetch_node import data_fetch_node
from app.core.nodes.data_planner_node import data_planner_node
from app.core.nodes.goal_hypothesis_node import goal_hypothesis_node
from app.core.nodes.router_node import router_node


REQUIRED_KEYS = {
    "status",
    "reasoning",
    "confidence_score",
    "next_action",
    "data",
    "errors",
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("node_fn", "state"),
    [
        (goal_hypothesis_node, {"user_query": "Is NVDA a good trade?"}),
        (
            data_checker_node,
            {
                "data_status": {
                    "ohlcv": {"available": True, "freshness": 1.0},
                    "news": {"available": True, "freshness": 1.0},
                    "fundamentals": {"available": True, "freshness": 1.0},
                    "macro": {"available": True, "freshness": 1.0},
                }
            },
        ),
        (data_planner_node, {"checker_output": {"missing_datasets": [], "stale_datasets": []}}),
        (data_fetch_node, {"data_plan": [{"dataset": "news", "priority": "P0"}]}),
    ],
)
async def test_nodes_return_common_contract(node_fn, state) -> None:
    result = await node_fn(state)
    assert REQUIRED_KEYS.issubset(result.keys())


@pytest.mark.asyncio
async def test_router_node_returns_common_contract() -> None:
    result = await router_node(
        {
            "goal": None,
            "confidence_score": 0.0,
            "iteration_count": 0,
            "retry_count_by_domain": {},
            "data_status": {},
            "tasks": [],
            "results": {},
            "critic_decision": None,
            "evidence_strength": 1.0,
        }
    )

    assert REQUIRED_KEYS.issubset(result.keys())
