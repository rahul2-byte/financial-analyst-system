import pytest
from unittest.mock import AsyncMock, MagicMock
from agents.data_access.market_online import MarketOnlineAgent
from agents.data_access.schemas import AgentResponse
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from data.providers.yfinance import YFinanceFetcher
from data.providers.rss_news import RSSNewsFetcher


@pytest.mark.asyncio
async def test_market_online_agent_flow():
    mock_yf = MagicMock(spec=YFinanceFetcher)
    mock_yf.fetch_stock_price.return_value = {"ticker": "RELIANCE.NS", "data": []}

    mock_rss = MagicMock(spec=RSSNewsFetcher)

    mock_llm = MagicMock(spec=LLMServiceInterface)

    first_llm_response = Message(
        role="assistant",
        content=None,
        tool_calls=[
            {
                "id": "call_456",
                "type": "function",
                "function": {
                    "name": "fetch_stock_price",
                    "arguments": '{"ticker": "RELIANCE"}',
                },
            }
        ],
    )

    second_llm_response = Message(
        role="assistant", content="The current price of RELIANCE is fetched."
    )

    mock_llm.generate_message = AsyncMock(
        side_effect=[first_llm_response, second_llm_response]
    )

    mock_sql = MagicMock()
    mock_vector = MagicMock()

    agent = MarketOnlineAgent(
        llm_service=mock_llm,
        yf_fetcher=mock_yf,
        rss_fetcher=mock_rss,
        sql_db=mock_sql,
        vector_db=mock_vector,
    )

    response = await agent.execute("What is the price of RELIANCE?")

    assert isinstance(response, AgentResponse)
    assert response.status == "success"
    assert "RELIANCE" in response.data["response"]

    mock_yf.fetch_stock_price.assert_called_once_with("RELIANCE", "1mo", "1d")
    assert mock_llm.generate_message.call_count == 2
