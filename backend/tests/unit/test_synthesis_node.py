import pytest

from agents.quality.synthesis_node import synthesis_node


@pytest.mark.asyncio
async def test_synthesis_uses_provisional_claims_before_verification() -> None:
    state = {
        "results": {
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
            },
            "sentiment_analysis": {
                "status": "ok",
                "claims": [
                    {
                        "claim_id": "c2",
                        "text": "Management tone is cautious",
                        "importance": "supporting",
                        "evidence_refs": ["cit2"],
                    }
                ],
            },
        },
        "claim_verification": None,
    }

    result = await synthesis_node(state)

    assert [claim["claim_id"] for claim in result["results"]["synthesis"]["claims"]] == [
        "c1",
        "c2",
    ]
    assert result["reasoning"] == "Synthesized research from 2 provisional claims."
    assert result["data"]["audit"]["decision_summary"]["provisional_claim_count"] == 2
    assert result["data"]["audit"]["decision_summary"]["verified_claim_count"] == 0


@pytest.mark.asyncio
async def test_synthesis_filters_to_verified_claims_after_critic_pass() -> None:
    state = {
        "results": {
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
            },
            "sentiment_analysis": {
                "status": "ok",
                "claims": [
                    {
                        "claim_id": "c2",
                        "text": "Management tone is cautious",
                        "importance": "supporting",
                        "evidence_refs": ["cit2"],
                    }
                ],
            },
        },
        "claim_verification": {"verified_claim_ids": ["c1"]},
    }

    result = await synthesis_node(state)

    assert [claim["claim_id"] for claim in result["results"]["synthesis"]["claims"]] == [
        "c1"
    ]
    assert result["reasoning"] == "Synthesized research from 1 verified claims."
    assert result["data"]["audit"]["decision_summary"]["provisional_claim_count"] == 0
    assert result["data"]["audit"]["decision_summary"]["verified_claim_count"] == 1


@pytest.mark.asyncio
async def test_synthesis_derives_evidence_strength_when_graph_state_has_default_zero() -> None:
    state = {
        "results": {
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
            }
        },
        "tool_registry": [
            {
                "extracted_metrics": {"score": 0.9, "pe_ratio": 12.0},
            }
        ],
        "claim_verification": None,
        "evidence_strength": 0.0,
    }

    result = await synthesis_node(state)

    assert result["evidence_strength"] > 0.0


@pytest.mark.asyncio
async def test_synthesis_zeroes_evidence_strength_when_verified_pass_has_no_claims() -> None:
    state = {
        "results": {
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
            }
        },
        "tool_registry": [
            {
                "extracted_metrics": {"score": 0.9, "pe_ratio": 12.0},
            }
        ],
        "claim_verification": {"verified_claim_ids": []},
        "evidence_strength": 0.0,
    }

    result = await synthesis_node(state)

    assert result["results"]["synthesis"]["claims"] == []
    assert result["evidence_strength"] == 0.0


@pytest.mark.asyncio
async def test_synthesis_preserves_non_zero_evidence_strength_for_verified_claims() -> None:
    state = {
        "results": {
            "fundamental_analysis": {
                "status": "ok",
                "claims": [
                    {
                        "claim_id": "c1",
                        "text": "Margins improved",
                        "importance": "major",
                        "evidence_refs": ["cit1"],
                    },
                    {
                        "claim_id": "c2",
                        "text": "Valuation is attractive",
                        "importance": "supporting",
                        "evidence_refs": ["cit2"],
                    },
                ],
            }
        },
        "claim_verification": {"verified_claim_ids": ["c1"]},
        "evidence_strength": 0.8,
    }

    result = await synthesis_node(state)

    assert [claim["claim_id"] for claim in result["results"]["synthesis"]["claims"]] == [
        "c1"
    ]
    assert result["evidence_strength"] == 0.8


@pytest.mark.asyncio
async def test_synthesis_uses_verified_claims_instead_of_keyword_scanning():
    state = {
        "results": {
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
                "findings": [
                    {
                        "finding_id": "f1",
                        "dimension": "profitability",
                        "summary": "Margins improved",
                        "evidence_ids": ["ev1"],
                        "unresolved": False,
                    }
                ],
                "confidence": 0.8,
            },
            "sentiment_analysis": {
                "status": "ok",
                "claims": [
                    {
                        "claim_id": "c2",
                        "text": "Management tone is cautious",
                        "importance": "supporting",
                        "evidence_refs": ["cit2"],
                    }
                ],
                "findings": [],
                "confidence": 0.6,
            },
        },
        "claim_verification": {"verified_claim_ids": ["c1", "c2"]},
    }

    result = await synthesis_node(state)

    assert result["results"]["synthesis"]["claims"]
    assert result["results"]["synthesis"]["decision"] in {
        "buy",
        "watchlist",
        "sell",
        "no_call",
    }
    assert "signal_mix" not in result["results"]["synthesis"]["key_drivers"][0]
