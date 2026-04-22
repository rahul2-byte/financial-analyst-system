import pytest

from agents.orchestration.validation_node import validation_node
from app.core.node_resources import resources


class _StubLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content
        self.tool_calls = None


class _StaticLLMService:
    def __init__(self, content: str) -> None:
        self.content = content

    async def generate_message(self, messages, model, tools=None):
        return _StubLLMResponse(self.content)


@pytest.mark.asyncio
async def test_validation_node_blocks_major_claim_without_verified_support():
    state = {
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
                        "evidence_refs": ["cit_1"],
                    }
                ],
            }
        },
        "confidence_score": 0.88,
        "claim_verification": {"verified_claim_ids": []},
    }

    result = await validation_node(state)

    assert result["status"] == "failure"
    assert any("major" in error.lower() for error in result["errors"])


@pytest.mark.asyncio
async def test_validation_allows_data_gap_claim_without_evidence_refs() -> None:
    state = {
        "goal": {"ticker": "INFY"},
        "results": {
            "fundamental_analysis": {"status": "ok", "claims": []},
            "synthesis": {
                "decision": "watchlist",
                "key_drivers": ["Debt data unavailable"],
                "risks": [],
                "data_used": {},
                "insufficiency_markers": [],
                "claims": [
                    {
                        "claim_id": "c_gap",
                        "text": "Unable to assess debt because debt-to-equity data is missing.",
                        "importance": "major",
                        "evidence_refs": [],
                    }
                ],
            }
        },
        "claim_verification": {"verified_claim_ids": ["c_gap"]},
        "confidence_score": 0.88,
        "evidence_strength": 0.8,
        "approved_agents": ["fundamental_analysis"],
    }

    result = await validation_node(state)

    assert result["status"] == "success"
    assert result["validation_passed"] is True


@pytest.mark.asyncio
async def test_validation_handles_none_claim_verification_without_crashing() -> None:
    state = {
        "results": {
            "synthesis": {
                "decision": "no_call",
                "key_drivers": [],
                "risks": [],
                "data_used": {},
                "insufficiency_markers": [],
                "claims": [],
            }
        },
        "claim_verification": None,
        "confidence_score": 0.1,
        "approved_agents": [],
        "evidence_strength": 0.0,
    }

    result = await validation_node(state)

    assert result["status"] in {"failure", "success"}


@pytest.mark.asyncio
async def test_validation_blocks_unresolved_conflict_for_directional_decision():
    state = {
        "results": {
            "synthesis": {
                "decision": "buy",
                "key_drivers": ["valuation"],
                "risks": [],
                "data_used": {},
                "insufficiency_markers": [],
                "claims": [
                    {"claim_id": "c1", "importance": "major", "evidence_refs": ["cit1"]}
                ],
            }
        },
        "claim_verification": {"verified_claim_ids": ["c1"]},
        "conflict_record": {
            "resolved": False,
            "unresolved_claim_pairs": [["c1", "c2"]],
        },
        "confidence_score": 0.9,
    }

    result = await validation_node(state)
    assert result["status"] == "failure"
    assert any("conflict" in error.lower() for error in result["errors"])


@pytest.mark.asyncio
async def test_validation_node_generates_narrative_final_report(monkeypatch):
    previous = resources._llm_service
    monkeypatch.setattr(
        resources,
        "_llm_service",
        _StaticLLMService("# Executive Summary\n\nNarrative report"),
    )
    try:
        state = {
            "user_query": "Analyze INFY",
            "goal": {"ticker": "INFY"},
            "approved_agents": ["fundamental_analysis"],
            "results": {
                "synthesis": {
                    "decision": "watchlist",
                    "key_drivers": ["earnings momentum"],
                    "risks": ["valuation risk"],
                    "data_used": {"fundamentals": {"available": True}},
                    "insufficiency_markers": [],
                    "claims": [
                        {
                            "claim_id": "c1",
                            "text": "INFY has resilient earnings quality",
                            "importance": "major",
                            "evidence_refs": ["cit_1"],
                        }
                    ],
                },
                "fundamental_analysis": {"summary": "Validated fundamentals"},
            },
            "claim_verification": {"verified_claim_ids": ["c1"]},
            "confidence_score": 0.88,
            "evidence_strength": 0.8,
            "data_status": {"fundamentals": {"available": True}},
        }

        result = await validation_node(state)
    finally:
        monkeypatch.setattr(resources, "_llm_service", previous)

    assert result["validation_passed"] is True
    assert result["final_output"]["decision"] == "watchlist"
    assert result["final_report"] == "# Executive Summary\n\nNarrative report"
