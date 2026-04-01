import pytest

from app.core.orchestrator import PipelineOrchestrator


@pytest.mark.asyncio
async def test_gated_nexus_full_flow() -> None:
    """Graph should terminate with structured final output contract."""
    orchestrator = PipelineOrchestrator()

    initial_state = {
        "user_query": "Research Reliance for 5 years",
        "conversation_history": [],
        "status": "initializing",
    }

    result = await orchestrator.research_graph.ainvoke(initial_state, {"recursion_limit": 40})

    assert result.get("final_output") is not None
    final_output = result["final_output"]
    assert "decision" in final_output
    assert "confidence_score" in final_output
    assert "risks" in final_output
    assert "data_used" in final_output
    assert "insufficiency_markers" in final_output
