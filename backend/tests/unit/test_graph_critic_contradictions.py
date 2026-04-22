import pytest

from agents.quality.critic_node import critic_node


@pytest.mark.asyncio
async def test_critic_emits_directional_conflict_record_with_strong_evidence() -> None:
    state = {
        "results": {
            "synthesis": {
                "claims": [
                    {
                        "claim_id": "c1",
                        "text": "Margins improved",
                        "importance": "major",
                        "evidence_refs": ["cit1"],
                        "contradicted_by": ["c2"],
                    },
                    {
                        "claim_id": "c2",
                        "text": "Margins declining",
                        "importance": "major",
                        "evidence_refs": ["cit2"],
                        "contradicted_by": ["c1"],
                    },
                ],
                "decision": "watchlist",
                "data_used": {
                    "ohlcv": {"freshness": 0.9},
                    "news": {"freshness": 0.9},
                },
            },
            "fundamental_analysis": {
                "status": "ok",
                "claims": [
                    {
                        "claim_id": "c1",
                        "text": "Margins improved",
                        "importance": "major",
                        "evidence_refs": ["cit1"],
                    }
                ],
                "confidence": 0.8,
            },
            "sentiment_analysis": {
                "status": "ok",
                "claims": [
                    {
                        "claim_id": "c2",
                        "text": "Margins declining",
                        "importance": "major",
                        "evidence_refs": ["cit2"],
                    }
                ],
                "confidence": 0.7,
            },
        },
        "tool_registry": [],
        "synthesis_confidence": 0.82,
        "evidence_strength": 0.78,
        "confidence_history": [0.71, 0.74],
        "confidence_components": {},
    }

    result = await critic_node(state)

    assert result["critic_decision"] == "conflict"
    assert result["conflict_record"]
    assert not result["conflict_record"]["resolved"]
    assert any(
        pair == ["c1", "c2"] or pair == ["c2", "c1"]
        for pair in result["conflict_record"]["unresolved_claim_pairs"]
    )


@pytest.mark.asyncio
async def test_critic_uses_evidence_gap_type_for_unsupported_conflict() -> None:
    state = {
        "results": {
            "synthesis": {
                "claims": [
                    {
                        "claim_id": "c1",
                        "text": "Major claim",
                        "importance": "major",
                        "evidence_refs": [],
                    }
                ],
                "decision": "buy",
                "data_used": {"ohlcv": {"freshness": 0.95}},
            },
        },
        "tool_registry": [],
        "synthesis_confidence": 0.76,
        "evidence_strength": 0.4,  # Low evidence strength
        "confidence_history": [0.7, 0.71],
        "confidence_components": {},
    }

    result = await critic_node(state)

    assert result["critic_decision"] == "retry"
    assert result["force_replan"] is True
