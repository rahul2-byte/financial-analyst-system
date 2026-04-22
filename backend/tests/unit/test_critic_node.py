import pytest

from agents.quality.critic_node import critic_node


@pytest.mark.asyncio
async def test_critic_requests_targeted_rerearch_for_invalid_citation_links():
    state = {
        "results": {
            "synthesis": {
                "claims": [
                    {
                        "claim_id": "c1",
                        "text": "Claim",
                        "importance": "major",
                        "evidence_refs": [],
                    }
                ],
                "decision": "buy",
                "data_used": {},
            }
        },
        "tool_registry": [],
        "confidence_score": 0.8,
        "tasks": [
            {
                "task_id": "sentiment_analysis",
                "agent": "sentiment_analysis",
                "priority": "P1",
                "parameters": {},
            }
        ],
    }

    result = await critic_node(state)

    assert result["critic_decision"] == "retry"
    assert result["force_replan"] is True
    assert any(
        task["parameters"].get("verification_focus")
        for task in result["replanned_tasks"]
    )


@pytest.mark.asyncio
async def test_critic_does_not_flag_data_gap_claim_as_hallucination() -> None:
    result = await critic_node(
        {
            "results": {
                "synthesis": {
                    "claims": [
                        {
                            "claim_id": "c-gap",
                            "text": "Unable to assess debt because debt-to-equity data is missing.",
                            "importance": "major",
                            "evidence_refs": [],
                        }
                    ],
                    "decision": "watchlist",
                    "data_used": {},
                }
            },
            "tool_registry": [],
            "confidence_score": 0.8,
            "tasks": [],
            "evidence_strength": 0.8,
        }
    )

    assert result["hallucination_issues"] == []
    assert result["claim_verification"]["verified_claim_ids"] == ["c-gap"]


@pytest.mark.asyncio
async def test_critic_increments_only_critic_retry_counter() -> None:
    result = await critic_node(
        {
            "results": {"synthesis": {"claims": [], "decision": "watchlist"}},
            "tool_registry": [],
            "confidence_score": 0.8,
            "tasks": [],
            "retry_count_by_domain": {"data_fetch": 1},
            "evidence_strength": 0.2,
        }
    )

    assert result["critic_decision"] == "retry"
    assert result["retry_count_by_domain"]["critic"] == 1
    assert result["retry_count_by_domain"]["data_fetch"] == 1


@pytest.mark.asyncio
async def test_critic_terminates_low_confidence_when_retry_limit_reached() -> None:
    result = await critic_node(
        {
            "results": {"synthesis": {"claims": [], "decision": "watchlist"}},
            "tool_registry": [],
            "confidence_score": 0.42,
            "tasks": [],
            "retry_count_by_domain": {"critic": 3},
            "evidence_strength": 0.1,
        }
    )

    assert result["critic_decision"] == "retry"
    assert result["next_action"] == "terminate_low_confidence"
