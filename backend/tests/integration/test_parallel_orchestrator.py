import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.orchestrator import PipelineOrchestrator
from agents.orchestration.schemas import (
    PlanResponse,
    PlanData,
    ExecutionStep,
    TargetAgent,
    AgentAction,
)
from agents.data_access.schemas import AgentResponse


@pytest.fixture
def mock_orchestrator():
    # Use patch to avoid initializing real services that might try to connect to DB/LLM or external APIs
    with patch("app.core.orchestrator.LlamaCppService"), patch(
        "app.core.orchestrator.PostgresClient"
    ), patch("app.core.orchestrator.QdrantStorage"), patch(
        "app.core.orchestrator.YFinanceFetcher"
    ), patch(
        "app.core.orchestrator.RSSNewsFetcher"
    ), patch(
        "app.core.orchestrator.langfuse_context"
    ):
        orch = PipelineOrchestrator()
        return orch


@pytest.mark.asyncio
async def test_execute_query_parallel_flow(mock_orchestrator):
    orchestrator = mock_orchestrator
    user_query = "Analyze Reliance industries"

    # 1. Mock Planner to return a 2-level DAG
    # Level 0: market_offline (Step 1), web_search (Step 2)
    # Level 1: fundamental_analysis (Step 3, depends on 1)

    plan_data = PlanData(
        plan_id="test_plan_123",
        is_financial_request=True,
        scope="single_stock",
        execution_steps=[
            ExecutionStep(
                step_number=1,
                target_agent=TargetAgent.MARKET_OFFLINE,
                action=AgentAction.FETCH_LOCAL_MARKET_DATA,
                parameters={"ticker": "RELIANCE"},
                dependencies=[],
            ),
            ExecutionStep(
                step_number=2,
                target_agent=TargetAgent.WEB_SEARCH,
                action=AgentAction.SEARCH_WEB,
                parameters={"query": "Reliance industries latest news"},
                dependencies=[],
            ),
            ExecutionStep(
                step_number=3,
                target_agent=TargetAgent.FUNDAMENTAL_ANALYSIS,
                action=AgentAction.ANALYZE_FUNDAMENTALS,
                parameters={"ticker": "RELIANCE"},
                dependencies=[1],
            ),
        ],
    )

    orchestrator.planner.generate_plan = AsyncMock(
        return_value=PlanResponse(status="success", data=plan_data, errors=None)
    )

    # Track execution order
    call_order = []

    async def mock_execute_market_offline(query):
        call_order.append("market_offline")
        # Add a tiny delay to simulate network/processing and check parallelism
        await asyncio.sleep(0.01)
        return AgentResponse(
            status="success",
            data={
                "response": "Offline data for Reliance: Price 2500, PE 25",
                "price": 2500,
                "pe": 25,
            },
            errors=None,
        )

    async def mock_execute_web_search(query):
        call_order.append("web_search")
        await asyncio.sleep(0.01)
        return AgentResponse(
            status="success",
            data={"response": "Latest news: Reliance expansion plan."},
            errors=None,
        )

    async def mock_execute_fundamental(query):
        call_order.append("fundamental_analysis")
        # Ensure that market_offline was called before this
        assert "market_offline" in call_order
        return AgentResponse(
            status="success",
            data={"response": "Fundamental Analysis: Strong buy based on PE 25."},
            errors=None,
        )

    orchestrator.market_offline.execute = AsyncMock(
        side_effect=mock_execute_market_offline
    )
    orchestrator.web_search.execute = AsyncMock(side_effect=mock_execute_web_search)
    orchestrator.fundamental.execute = AsyncMock(side_effect=mock_execute_fundamental)

    # Mock LLM for synthesis
    orchestrator.llm.generate = AsyncMock(return_value="Final Synthesis Report")

    # Mock Verification Agent
    orchestrator.verification_agent.verify = MagicMock()
    orchestrator.verification_agent.verify.return_value.is_valid = True

    # Mock Validator Agent
    orchestrator.validator.execute = AsyncMock(
        return_value=AgentResponse(
            status="success",
            data={"is_valid": True, "final_approved_text": "Final Verified Report"},
            errors=None,
        )
    )

    # Patch _synthesize_report to capture state
    with patch.object(
        PipelineOrchestrator,
        "_synthesize_report",
        wraps=orchestrator._synthesize_report,
    ) as mock_synth:
        # 3. Execute - Consume the async generator
        events = []
        async for event in orchestrator.execute_query(user_query):
            events.append(event)

        # The last event should be the final report
        final_report_event = events[-1]
        assert final_report_event["type"] == "text_delta"
        result = final_report_event["content"]

        # 4. Asserts
        assert result == "Final Verified Report"

        # Verify all agents were called
        assert orchestrator.market_offline.execute.called
        assert orchestrator.web_search.execute.called
        assert orchestrator.fundamental.execute.called

        # Verify Level 1 started after Level 0
        # mo_idx and ws_idx should be 0 or 1 in call_order (can vary)
        # fa_idx should be 2.
        mo_idx = call_order.index("market_offline")
        ws_idx = call_order.index("web_search")
        fa_idx = call_order.index("fundamental_analysis")

        assert fa_idx > mo_idx
        # web_search could also be before or after market_offline, but it must be before its own dependent levels (none here)
        # and since it's in Level 0, it should be before Level 1 agents.
        assert fa_idx > ws_idx

        # Check ResearchState
        state = mock_synth.call_args[0][1]
        assert state.query == user_query
        assert "1" in state.agent_outputs
        assert "2" in state.agent_outputs
        assert "3" in state.agent_outputs
        assert "Price 2500" in state.agent_outputs["1"]

        # Check tool registry and metric extraction
        assert len(state.tool_registry) == 3
        market_tool_result = next(
            (
                tr
                for tr in state.tool_registry
                if tr.tool_name == "agent_market_offline"
            ),
            None,
        )
        assert market_tool_result is not None
        assert market_tool_result.extracted_metrics["price"] == 2500.0
        assert market_tool_result.extracted_metrics["pe"] == 25.0

        fundamental_tool_result = next(
            (
                tr
                for tr in state.tool_registry
                if tr.tool_name == "agent_fundamental_analysis"
            ),
            None,
        )
        assert fundamental_tool_result is not None
        assert (
            fundamental_tool_result.output_data["response"]
            == "Fundamental Analysis: Strong buy based on PE 25."
        )
