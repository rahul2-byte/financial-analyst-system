import pytest

from agents.financial.research.research_plan_node import research_plan_node


@pytest.mark.asyncio
async def test_research_plan_resets_claim_verification_on_replan() -> None:
    result = await research_plan_node(
        {
            "user_query": "Analyze HDFCBANK",
            "goal": {"ticker": "HDFCBANK"},
            "approved_agents": ["fundamental_analysis"],
            "claim_verification": {"verified_claim_ids": ["old-claim"]},
            "critic_decision": "retry",
            "task_contexts": {"fundamental_analysis": {"old": True}},
            "results": {"synthesis": {"decision": "no_call"}},
            "validation_passed": True,
            "evaluation_passed": True,
            "evaluation_result": {"score": 0.95},
            "final_output": {"decision": "watchlist"},
            "final_report": "old report",
        }
    )

    assert result["claim_verification"] is None
    assert result["critic_decision"] is None
    assert result["task_contexts"] == {}
    assert result["results"]["synthesis"] is None
    assert result["results"]["fundamental_analysis"] is None
    assert result["validation_passed"] is False
    assert result["evaluation_passed"] is False
    assert result["evaluation_result"] == {}
    assert result["final_output"] is None
    assert result["final_report"] is None
