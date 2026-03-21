import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from agents.analysis.sentiment import SentimentAnalysisAgent
from agents.analysis.schemas import AgentResponse
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message


@pytest.mark.asyncio
async def test_sentiment_agent_flow():
    mock_llm = MagicMock(spec=LLMServiceInterface)

    # First call: LLM decides to use the FinBERT tool
    first_llm_response = Message(
        role="assistant",
        content=None,
        tool_calls=[
            {
                "id": "call_111",
                "type": "function",
                "function": {
                    "name": "run_finbert_analysis",
                    "arguments": '{"text": "Tata Motors expects massive growth in EVs next quarter. However, the battery supplier is facing a lawsuit."}',
                },
            }
        ],
    )

    # Second call: LLM outputs the strict QualitativeInsights JSON
    fake_json_output = {
        "finbert_overall_score": "Slightly Bullish (60%)",
        "finbert_guidance_score": "Strongly Bullish (90%)",
        "order_book_updates": ["Massive growth in EVs expected next quarter."],
        "major_challenges": ["Battery supplier is facing a lawsuit."],
        "entity_impact_map": [
            {
                "entity_name": "Battery Supplier",
                "relationship": "Supplier",
                "impact": "Bearish",
            }
        ],
        "is_contradictory": True,
        "contradiction_reason": "Guidance is bullish but supplier lawsuit poses severe supply chain risk.",
        "executive_summary": "Tata Motors has strong EV guidance, but the supply chain is at risk due to a supplier lawsuit.",
    }

    second_llm_response = Message(
        role="assistant", content=json.dumps(fake_json_output)
    )

    mock_llm.generate_message = AsyncMock(
        side_effect=[first_llm_response, second_llm_response]
    )

    # Initialize Agent
    agent = SentimentAnalysisAgent(llm_service=mock_llm)

    # Execute Agent (We mock the NLPScorer's actual model load by just passing text and letting the mock handle the loop)
    # The NLPScorer tool execution inside the agent will fail gracefully because Transformers isn't loaded in test,
    # but the test proves the AGENT loop and schema extraction works.

    response = await agent.execute(
        user_query="Analyze this news.",
        raw_text_data="Tata Motors expects massive growth in EVs next quarter. However, the battery supplier is facing a lawsuit.",
    )

    # Assertions
    assert isinstance(response, AgentResponse)
    assert response.status == "success"

    # Check if the strict JSON was parsed into the data dict
    data = response.data
    assert "finbert_overall_score" in data
    assert "order_book_updates" in data
    assert data["is_contradictory"] is True
    assert len(data["entity_impact_map"]) == 1
    assert data["entity_impact_map"][0]["impact"] == "Bearish"

    # Verify LLM was called twice
    assert mock_llm.generate_message.call_count == 2
