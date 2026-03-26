import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from agents.research.web_search import WebSearchAgent
from agents.research.schemas import AgentResponse
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from data.providers.web_search import WebSearchProvider  # Import the actual provider


@pytest.mark.asyncio
async def test_web_search_agent_flow():
    mock_llm = MagicMock(spec=LLMServiceInterface)

    # 1. First call: LLM decides to search
    first_llm_response = Message(
        role="assistant",
        content=None,
        tool_calls=[
            {
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "search_latest_news",
                    "arguments": '{"query": "RBI repo rate"}',
                },
            }
        ],
    )

    # 2. Second call (after tool result): LLM says it's ready (no more tool calls)
    second_llm_response = Message(role="assistant", content="I have found the info.")

    # 3. Third call (Final synthesis): LLM outputs the strict WebResearchResult JSON
    fake_json_output = {
        "summary_of_findings": "The RBI kept the repo rate unchanged at 6.5%.",
        "is_breaking_news_detected": True,
        "potential_market_impact": "Neutral",
        "citations": [
            {
                "title": "RBI keeps repo rate unchanged",
                "url": "https://example.com/rbi-news",
                "key_fact_extracted": "Repo rate unchanged at 6.5%",
            }
        ],
    }

    third_llm_response = Message(role="assistant", content=json.dumps(fake_json_output))

    # Set the sequence of responses for the LLM
    mock_llm.generate_message = AsyncMock(
        side_effect=[first_llm_response, second_llm_response, third_llm_response]
    )

    # Mock the WebSearchProvider completely
    mock_web_provider = MagicMock(spec=WebSearchProvider)
    mock_web_provider.search_latest_news.return_value = [
        {
            "title": "RBI keeps repo rate unchanged",
            "url": "https://example.com/rbi-news",
            "body": "Repo rate unchanged at 6.5%",
        }
    ]

    # Instantiate the agent with the mocked provider
    agent = WebSearchAgent(llm_service=mock_llm, provider=mock_web_provider)

    response = await agent.execute(user_query="What is the latest RBI repo rate?")

    # Assertions
    assert isinstance(response, AgentResponse)
    assert response.status == "success"

    data = response.data
    assert "summary_of_findings" in data
    assert data["is_breaking_news_detected"] is True
    assert data["potential_market_impact"] == "Neutral"
    assert len(data["citations"]) == 1

    # Verify LLM was called 3 times
    assert mock_llm.generate_message.call_count == 3

    # Verify the provider was called correctly
    mock_web_provider.search_latest_news.assert_called_once_with(
        "RBI repo rate", time_range="w"
    )


@pytest.mark.asyncio
async def test_web_search_agent_retries_final_json_parse_failure():
    mock_llm = MagicMock(spec=LLMServiceInterface)

    first_llm_response = Message(
        role="assistant",
        content=None,
        tool_calls=[
            {
                "id": "call_retry_1",
                "type": "function",
                "function": {
                    "name": "search_latest_news",
                    "arguments": '{"query": "Tata Motors"}',
                },
            }
        ],
    )
    second_llm_response = Message(role="assistant", content="I have enough sources.")
    third_llm_response = Message(
        role="assistant",
        content='```json\n{"summary_of_findings": "Bad\nJSON", "is_breaking_news_detected": true}\n```',
    )
    fourth_llm_response = Message(
        role="assistant",
        content=json.dumps(
            {
                "summary_of_findings": "Validated findings.",
                "is_breaking_news_detected": False,
                "potential_market_impact": "Neutral",
                "citations": [],
            }
        ),
    )

    mock_llm.generate_message = AsyncMock(
        side_effect=[
            first_llm_response,
            second_llm_response,
            third_llm_response,
            fourth_llm_response,
        ]
    )

    mock_web_provider = MagicMock(spec=WebSearchProvider)
    mock_web_provider.search_latest_news.return_value = [
        {"title": "ok", "url": "https://example.com"}
    ]

    agent = WebSearchAgent(llm_service=mock_llm, provider=mock_web_provider)
    response = await agent.execute(user_query="Retry JSON parse flow")

    assert response.status == "success"
    assert response.data["summary_of_findings"] == "Validated findings."
    assert mock_llm.generate_message.call_count == 4


@pytest.mark.asyncio
async def test_web_search_agent_sanitizes_invalid_time_range():
    mock_llm = MagicMock(spec=LLMServiceInterface)
    mock_web_provider = MagicMock(spec=WebSearchProvider)
    mock_web_provider.search_latest_news.return_value = []

    agent = WebSearchAgent(llm_service=mock_llm, provider=mock_web_provider)
    _ = agent._execute_tool(
        "search_latest_news",
        {"query": "Tata Motors", "time_range": "d90"},
    )

    mock_web_provider.search_latest_news.assert_called_once_with(
        "Tata Motors",
        time_range="m",
    )
