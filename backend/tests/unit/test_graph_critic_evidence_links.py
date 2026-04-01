import pytest

from app.core.graph.nodes.autonomous_quality_nodes import autonomous_critic_node


@pytest.mark.asyncio
async def test_critic_retries_when_synthesis_claim_has_no_evidence_refs() -> None:
    state = {
        "results": {
            "synthesis": {
                "key_drivers": ["signal_mix=['bullish', 'neutral', 'neutral']"],
                "data_used": {"ohlcv": {"freshness": 0.9}},
                "claims": [
                    {
                        "claim_id": "c1",
                        "text": "Momentum is improving",
                        "evidence_refs": [],
                    }
                ],
            },
            "fundamental_analysis": {"analysis": "buy"},
            "sentiment_analysis": {"analysis": "neutral"},
            "macro_analysis": {"analysis": "neutral"},
        },
        "tool_registry": [
            {
                "tool_name": "analysis:run_fundamental_scan",
                "extracted_metrics": {"rsi": 61.0},
            }
        ],
        "synthesis_confidence": 0.74,
        "evidence_strength": 0.7,
        "confidence_history": [0.69, 0.7],
        "confidence_components": {},
    }

    result = await autonomous_critic_node(state)

    assert result["critic_decision"] == "retry"
    assert result["hallucination_issues"]
    assert result["hallucination_issues"][0]["claim_id"] == "c1"


@pytest.mark.asyncio
async def test_critic_approves_when_all_claims_have_evidence_refs() -> None:
    state = {
        "results": {
            "synthesis": {
                "key_drivers": ["signal_mix=['bullish', 'neutral', 'neutral']"],
                "data_used": {"ohlcv": {"freshness": 0.9}},
                "claims": [
                    {
                        "claim_id": "c1",
                        "text": "Momentum is improving",
                        "evidence_refs": ["analysis:run_fundamental_scan:rsi"],
                    }
                ],
            },
            "fundamental_analysis": {"analysis": "buy"},
            "sentiment_analysis": {"analysis": "neutral"},
            "macro_analysis": {"analysis": "neutral"},
        },
        "tool_registry": [
            {
                "tool_name": "analysis:run_fundamental_scan",
                "extracted_metrics": {"rsi": 61.0},
            }
        ],
        "synthesis_confidence": 0.8,
        "evidence_strength": 0.8,
        "confidence_history": [0.72, 0.75],
        "confidence_components": {},
    }

    result = await autonomous_critic_node(state)

    assert result["critic_decision"] in {"approve", "conflict"}
    assert result["hallucination_issues"] == []
