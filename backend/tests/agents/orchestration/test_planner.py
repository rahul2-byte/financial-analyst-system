import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from agents.orchestration.planner import PlannerAgent
from app.services.llm_interface import LLMServiceInterface
from agents.orchestration.schemas import PlanResponse, PlanData
from agents.data_access.schemas import AgentResponse


@pytest.mark.asyncio
async def test_planner_agent_success():
    # Mock LLM service
    mock_llm = MagicMock(spec=LLMServiceInterface)

    # Define a valid fake JSON response from the LLM
    fake_json_response = {
        "plan_id": "test_123",
        "is_financial_request": True,
        "scope": "single_stock",
        "execution_steps": [
            {
                "step_number": 1,
                "target_agent": "market_offline",
                "action": "fetch_local_market_data",
                "parameters": {"ticker": "AAPL"},
                "dependencies": [],
            }
        ],
    }

    # Mock the generate method to return our fake JSON string asynchronously
    mock_llm.generate = AsyncMock(return_value=json.dumps(fake_json_response))

    agent = PlannerAgent(llm_service=mock_llm)
    response = await agent.execute(user_query="Check Apple stock data")

    # Assertions
    assert isinstance(response, AgentResponse)
    assert response.status == "success"
    assert response.data is not None
    assert response.data["plan_id"] == "test_123"
    assert len(response.data["execution_steps"]) == 1
    assert response.data["execution_steps"][0]["target_agent"] == "market_offline"


@pytest.mark.asyncio
async def test_planner_agent_failure():
    # Mock LLM service
    mock_llm = MagicMock(spec=LLMServiceInterface)

    # Simulate an error (e.g., invalid JSON returned by LLM or connection error)
    mock_llm.generate = AsyncMock(side_effect=Exception("LLM connection failed"))

    agent = PlannerAgent(llm_service=mock_llm)
    response = await agent.execute(user_query="Check Apple stock data")

    # Assertions
    assert isinstance(response, AgentResponse)
    assert response.status == "failure"
    assert response.data == {}
    assert response.errors is not None
    assert "LLM connection failed" in response.errors[0]
