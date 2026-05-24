import pytest

from agents.financial.data.data_plan_node import data_plan_node


@pytest.mark.asyncio
async def test_data_plan_node_attaches_timeframe_requirements() -> None:
    result = await data_plan_node(
        {
            "data_check": {
                "missing_datasets": ["ohlcv"],
                "stale_datasets": [],
            },
            "timeframe_policy": {
                "ohlcv": {
                    "period": "5y",
                    "interval": "1d",
                    "expected_points": 1260,
                    "minimum_coverage_ratio": 0.8,
                    "stale_after_days": 5,
                }
            },
        }
    )

    assert result["data_plan"][0]["requirements"]["period"] == "5y"


@pytest.mark.asyncio
async def test_data_plan_node_prioritizes_materialize_for_missing() -> None:
    result = await data_plan_node(
        {
            "data_check": {
                "missing_datasets": ["ohlcv"],
                "stale_datasets": [],
            },
            "timeframe_policy": {"ohlcv": {"period": "1y"}},
        }
    )

    assert result["data_plan"][0]["dataset"] == "ohlcv"
    assert result["data_plan"][0]["action"] == "materialize"
    assert result["data_plan"][0]["priority"] == "P0"
