import pytest

from app.core.graph.nodes.autonomous_goal_node import autonomous_goal_node


@pytest.mark.asyncio
async def test_goal_extracts_company_alias_ticker_not_stopword() -> None:
    result = await autonomous_goal_node({"user_query": "Research Reliance for 5 years"})
    assert result["goal"]["ticker"] == "RELIANCE.NS"


@pytest.mark.asyncio
async def test_goal_extracts_symbol_token() -> None:
    result = await autonomous_goal_node({"user_query": "Is AAPL a good trade?"})
    assert result["goal"]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_goal_handles_dot_symbol_token() -> None:
    result = await autonomous_goal_node({"user_query": "Should I buy BRK.B now?"})
    assert result["goal"]["ticker"] == "BRK.B"


@pytest.mark.asyncio
async def test_goal_returns_none_when_query_has_no_ticker() -> None:
    result = await autonomous_goal_node(
        {"user_query": "What are the macro risks over next quarter?"}
    )
    assert result["goal"]["ticker"] is None
