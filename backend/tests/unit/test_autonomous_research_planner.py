import pytest

from agents.financial.research.research_plan_node import research_plan_node


@pytest.mark.asyncio
async def test_research_planner_filters_tasks_by_approved_agents() -> None:
    state = {
        "user_query": "Analyze AAPL",
        "goal": {"ticker": "AAPL", "instruments": [{"trading_symbol": "AAPL"}]},
        "approved_agents": ["macro_analysis", "fundamental_analysis"],
        "timeframe": "5y",
        "replanned_tasks": [],
        "confidence_score": 0.5,
    }

    result = await research_plan_node(state)

    tasks = result["tasks"]
    assert [task["agent"] for task in tasks] == [
        "fundamental_analysis",
        "macro_analysis",
    ]
    for task in tasks:
        assert task["parameters"]["timeframe"] == "5y"


@pytest.mark.asyncio
async def test_research_planner_defaults_to_full_agent_set_when_not_approved() -> None:
    state = {
        "user_query": "Analyze AAPL",
        "goal": {"ticker": "AAPL", "instruments": [{"trading_symbol": "AAPL"}]},
        "approved_agents": [],
        "timeframe": "1y",
        "replanned_tasks": [],
        "confidence_score": 0.5,
    }

    result = await research_plan_node(state)

    agents = {task["agent"] for task in result["tasks"]}
    assert agents == {
        "fundamental_analysis",
        "sentiment_analysis",
        "macro_analysis",
        "technical_analysis",
        "contrarian_analysis",
    }


@pytest.mark.asyncio
async def test_research_planner_maps_fetched_data_into_agent_parameters() -> None:
    state = {
        "user_query": "Analyze AAPL",
        "goal": {"ticker": "AAPL", "instruments": [{"trading_symbol": "AAPL"}]},
        "approved_agents": [],
        "timeframe": "1y",
        "replanned_tasks": [],
        "confidence_score": 0.5,
        "fetched_data": {
            "ohlcv": {"by_symbol": {"AAPL": {"data": [{"Date": "2026-04-01"}]}}},
            "fundamentals": {"by_symbol": {"AAPL": {"marketCap": 100}}},
            "news": [{"title": "AAPL news", "summary": "earnings beat"}],
            "macro": {"USD_INR": 83.1},
        },
    }

    result = await research_plan_node(state)

    tasks = {task["agent"]: task for task in result["tasks"]}
    assert tasks["fundamental_analysis"]["parameters"]["raw_data"]["marketCap"] == 100
    assert tasks["technical_analysis"]["parameters"]["ohlcv_data"] == [
        {"Date": "2026-04-01"}
    ]
    assert "AAPL news" in tasks["sentiment_analysis"]["parameters"]["text"]
    assert tasks["macro_analysis"]["parameters"]["macro_data"]["USD_INR"] == 83.1
    assert (
        tasks["contrarian_analysis"]["parameters"]["market_data"]["fundamentals"][
            "marketCap"
        ]
        == 100
    )
