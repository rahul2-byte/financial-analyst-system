import pytest

from app.core.graph.nodes.autonomous_validation_node import autonomous_validation_node


@pytest.mark.asyncio
async def test_validation_fails_when_synthesis_payload_missing() -> None:
    result = await autonomous_validation_node(
        {
            "confidence_score": 0.8,
            "results": {},
            "goal": {"objective": "test"},
        }
    )

    assert result["status"] == "failure"
    assert result["validation_passed"] is False


@pytest.mark.asyncio
async def test_validation_fails_when_claim_has_no_evidence_refs() -> None:
    result = await autonomous_validation_node(
        {
            "confidence_score": 0.82,
            "goal": {"objective": "test"},
            "results": {
                "synthesis": {
                    "decision": "buy",
                    "key_drivers": ["metric:rsi"],
                    "risks": ["volatility"],
                    "data_used": {"ohlcv": {"available": True}},
                    "insufficiency_markers": [],
                    "claims": [
                        {
                            "claim_id": "c1",
                            "text": "Momentum improving",
                            "evidence_refs": [],
                        }
                    ],
                }
            },
        }
    )

    assert result["status"] == "failure"
    assert result["validation_passed"] is False
