import pytest
from unittest.mock import AsyncMock, patch

from app.core.orchestrator import PipelineOrchestrator
from agents.data_access.schemas import AgentResponse


@pytest.fixture
def mock_orchestrator():
    with patch("app.core.orchestrator.LlamaCppService"), patch(
        "app.core.orchestrator.PostgresClient"
    ), patch("app.core.orchestrator.QdrantStorage"), patch(
        "app.core.orchestrator.YFinanceFetcher"
    ), patch(
        "app.core.orchestrator.RSSNewsFetcher"
    ), patch(
        "app.core.orchestrator.langfuse_context"
    ):
        return PipelineOrchestrator()


def _collect_token_text(events: list[dict]) -> str:
    return "".join(
        event["data"]["content"]
        for event in events
        if event.get("event") == "token" and isinstance(event.get("data"), dict)
    )


@pytest.mark.asyncio
async def test_greeting_routes_through_planner_and_skips_pipeline(mock_orchestrator):
    orchestrator = mock_orchestrator

    orchestrator.planner.execute = AsyncMock(
        return_value=AgentResponse(
            status="success",
            data={
                "plan_id": "intent_1",
                "intent_type": "greeting",
                "response_mode": "direct_response",
                "assistant_response": "Hello! How can I help with your finance questions today?",
                "is_financial_request": False,
                "scope": "greeting",
                "execution_steps": [],
            },
            errors=None,
        )
    )

    orchestrator.market_offline.execute = AsyncMock()
    orchestrator.web_search.execute = AsyncMock()

    events = []
    async for event in orchestrator.execute_query("hi"):
        events.append(event)

    assert orchestrator.planner.execute.called
    assert not orchestrator.market_offline.execute.called
    assert not orchestrator.web_search.execute.called
    assert "Hello!" in _collect_token_text(events)


@pytest.mark.asyncio
async def test_clarification_mode_skips_pipeline(mock_orchestrator):
    orchestrator = mock_orchestrator

    orchestrator.planner.execute = AsyncMock(
        return_value=AgentResponse(
            status="success",
            data={
                "plan_id": "intent_2",
                "intent_type": "complex_research",
                "response_mode": "ask_clarification",
                "assistant_response": "Before I proceed, which market and timeframe should I focus on?",
                "is_financial_request": True,
                "scope": "unclear",
                "execution_steps": [],
            },
            errors=None,
        )
    )

    orchestrator.market_offline.execute = AsyncMock()
    orchestrator.web_search.execute = AsyncMock()

    events = []
    async for event in orchestrator.execute_query("analyze semiconductors"):
        events.append(event)

    assert not orchestrator.market_offline.execute.called
    assert not orchestrator.web_search.execute.called
    assert "timeframe" in _collect_token_text(events)
