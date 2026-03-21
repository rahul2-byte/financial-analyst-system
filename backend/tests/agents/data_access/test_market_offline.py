import pytest
from unittest.mock import AsyncMock, MagicMock
from agents.data_access.market_offline import MarketOfflineAgent
from agents.data_access.schemas import AgentResponse
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from storage.sql.client import PostgresClient


@pytest.mark.asyncio
async def test_market_offline_agent_flow():
    # Mock Database Client
    mock_db = MagicMock(spec=PostgresClient)
    mock_db.is_db_up.return_value = True

    # Mock LLM Service
    mock_llm = MagicMock(spec=LLMServiceInterface)

    # Simulate LLM returning a tool call
    first_llm_response = Message(
        role="assistant",
        content=None,
        tool_calls=[
            {
                "id": "call_123",
                "type": "function",
                "function": {"name": "check_db_status", "arguments": "{}"},
            }
        ],
    )

    # Simulate LLM generating the final text response after getting the tool result
    second_llm_response = Message(
        role="assistant", content="The database is up and running."
    )

    mock_llm.generate_message = AsyncMock(
        side_effect=[first_llm_response, second_llm_response]
    )

    # Initialize Agent
    agent = MarketOfflineAgent(llm_service=mock_llm, db_client=mock_db)

    # Execute Agent
    response = await agent.execute("Is the DB up?")

    # Assertions
    assert isinstance(response, AgentResponse)
    assert response.status == "success"
    assert "The database is up and running." in response.data["response"]

    # Verify DB was actually called
    mock_db.is_db_up.assert_called_once()

    # Verify LLM was called twice (once for tool call, once for final response)
    assert mock_llm.generate_message.call_count == 2
