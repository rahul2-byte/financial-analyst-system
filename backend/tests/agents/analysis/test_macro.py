import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.analysis.macro import MacroAnalysisAgent
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message


@pytest.mark.asyncio
async def test_macro_agent_retries_on_invalid_json_then_succeeds():
    mock_llm = MagicMock(spec=LLMServiceInterface)

    invalid_json_response = Message(
        role="assistant",
        content='```json\n{"overall_macro_outlook": "Bad\nJSON"}\n```',
    )
    valid_json_response = Message(
        role="assistant",
        content=json.dumps(
            {
                "summary": "Macro backdrop remains mixed.",
                "impact_on_markets": "Neutral to mildly bearish due to rate uncertainty.",
                "key_indicators": {
                    "inflation": "sticky",
                    "policy_rate": "elevated",
                },
                "risk_level": "Moderate",
            }
        ),
    )

    mock_llm.generate_message = AsyncMock(
        side_effect=[invalid_json_response, valid_json_response]
    )

    agent = MacroAnalysisAgent(llm_service=mock_llm)
    response = await agent.execute("Analyze macro risk for Tata Motors")

    assert response.status == "success"
    assert response.data["risk_level"] == "Moderate"
    assert mock_llm.generate_message.call_count == 2
