import pytest

from app.core.nodes.critic_node import critic_node
from app.core.nodes.reflection_node import reflection_node


@pytest.mark.asyncio
async def test_critic_forces_retry_on_low_evidence() -> None:
    state = {
        "synthesis_confidence": 0.8,
        "evidence_strength": 0.3,
        "confidence_components": {"freshness_penalty": 0.05, "contradiction_penalty": 0.05},
        "confidence_history": [0.6, 0.62],
    }

    result = await critic_node(state)

    assert result["critic_decision"] == "retry"
    assert result["confidence_score"] == result["smoothed_confidence"]


@pytest.mark.asyncio
async def test_reflection_increments_research_retry_counter() -> None:
    result = await reflection_node({"retry_count_by_domain": {"research": 1}, "confidence_score": 0.5})

    assert result["retry_count_by_domain"]["research"] == 2
    assert result["next_action"] == "run_research_plan"
