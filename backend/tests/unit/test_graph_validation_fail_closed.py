import pytest

from agents.orchestration.validation_node import validation_node


@pytest.mark.asyncio
async def test_validation_fails_when_synthesis_payload_missing() -> None:
    result = await validation_node(
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
    result = await validation_node(
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


@pytest.mark.asyncio
async def test_validation_fails_when_major_claim_lacks_verified_support() -> None:
    result = await validation_node(
        {
            "results": {
                "synthesis": {
                    "decision": "buy",
                    "key_drivers": ["earnings momentum"],
                    "risks": [],
                    "data_used": {"fundamentals": {"available": True}},
                    "insufficiency_markers": [],
                    "claims": [
                        {
                            "claim_id": "c_major",
                            "text": "INFY should be bought now",
                            "importance": "major",
                            "evidence_refs": ["ev1"],
                        }
                    ],
                }
            },
            "confidence_score": 0.88,
            "goal": {"objective": "Assess INFY earnings risk"},
            "claim_verification": {"verified_claim_ids": []},
        }
    )

    assert result["status"] == "failure"
    assert any("major" in error.lower() for error in result["errors"])
