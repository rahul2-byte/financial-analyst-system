import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from agents.analysis.fundamental import FundamentalAnalysisAgent
from agents.analysis.schemas import AgentResponse
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message


@pytest.mark.asyncio
async def test_fundamental_agent_flow():
    mock_llm = MagicMock(spec=LLMServiceInterface)

    # Simulate LLM deciding to use the scan tool
    first_llm_response = Message(
        role="assistant",
        content=None,
        tool_calls=[
            {
                "id": "call_789",
                "type": "function",
                "function": {
                    "name": "run_fundamental_scan",
                    "arguments": json.dumps(
                        {
                            "raw_data": '{"peRatio": 12, "priceToBook": 1.5, "debtToEquity": 1.2, "profitMargins": 0.18, "returnOnEquity": 0.20}'
                        }
                    ),
                },
            }
        ],
    )

    # Simulate LLM writing the final thesis based on the tool result
    second_llm_response = Message(
        role="assistant",
        content="Based on the analysis, the company is undervalued with a P/E of 12, has moderate leverage, and shows excellent profitability.",
    )

    mock_llm.generate_message = AsyncMock(
        side_effect=[first_llm_response, second_llm_response]
    )

    agent = FundamentalAnalysisAgent(llm_service=mock_llm)

    # Execute Agent
    test_data = {
        "peRatio": 12,
        "priceToBook": 1.5,
        "debtToEquity": 1.2,
        "profitMargins": 0.18,
        "returnOnEquity": 0.20,
    }

    response = await agent.execute(
        "Write an investment thesis.", raw_fundamental_data=test_data
    )

    # Assertions
    assert isinstance(response, AgentResponse)
    assert response.status == "success"
    assert "undervalued" in response.data["response"]

    # Verify LLM was called twice
    assert mock_llm.generate_message.call_count == 2
