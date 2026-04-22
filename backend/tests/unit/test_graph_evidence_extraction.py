import pytest

from agents.quality.synthesis_node import synthesis_node
from agents.financial.research.research_execution_node import research_execution_node


@pytest.mark.asyncio
async def test_research_execution_collects_tool_registry_evidence(monkeypatch) -> None:
    async def _fake_agent(_state, _resources):
        return {
            "agent_outputs": {"fundamental_analysis": {"findings": []}},
            "tool_registry": [
                {
                    "tool_name": "analysis:run_fundamental_scan",
                    "input_parameters": {},
                    "output_data": {"score": 0.9, "pe_ratio": 12.0},
                    "extracted_metrics": {"score": 0.9, "pe_ratio": 12.0},
                }
            ],
        }

    # Patch the AGENT_NODE_MAP in agents.financial.research.research_execution_node
    import agents.financial.research.research_execution_node as exec_module

    monkeypatch.setitem(
        exec_module.AGENT_NODE_MAP,
        "fundamental_analysis",
        _fake_agent,
    )

    result = await research_execution_node(
        {
            "tasks": [
                {
                    "task_id": "fundamental_analysis",
                    "agent": "fundamental_analysis",
                    "priority": "P0",
                    "parameters": {"ticker": "AAPL"},
                }
            ],
            "timeouts": {"task_timeout_s": 5.0, "stage_timeout_s": 10.0},
            "results": {},
            "approved_agents": ["fundamental_analysis"],
            "required_agents": [],
        }
    )

    assert result["tool_registry"]
    assert result["tool_registry"][0]["extracted_metrics"]["pe_ratio"] == 12.0


@pytest.mark.asyncio
async def test_synthesis_uses_verified_claims_instead_of_keyword_scanning() -> None:
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
                "findings": [],
                "confidence": 0.8,
            },
        },
        "claim_verification": {"verified_claim_ids": ["c1"]},
        "data_status": {},
    }

    result = await synthesis_node(state)

    assert result["results"]["synthesis"]["claims"]
    assert result["results"]["synthesis"]["decision"] == "watchlist"


@pytest.mark.asyncio
async def test_research_execution_preserves_agent_mapping_when_earlier_task_times_out(
    monkeypatch,
) -> None:
    import asyncio

    async def _slow_agent(_state, _resources):
        await asyncio.sleep(0.2)
        return {"agent_outputs": {"fundamental_analysis": {"findings": []}}}

    async def _fast_agent(_state, _resources):
        return {"agent_outputs": {"sentiment_analysis": {"findings": []}}}

    import agents.financial.research.research_execution_node as exec_module

    monkeypatch.setitem(exec_module.AGENT_NODE_MAP, "fundamental_analysis", _slow_agent)
    monkeypatch.setitem(exec_module.AGENT_NODE_MAP, "sentiment_analysis", _fast_agent)

    result = await research_execution_node(
        {
            "tasks": [
                {
                    "task_id": "fundamental_analysis",
                    "agent": "fundamental_analysis",
                    "priority": "P0",
                    "parameters": {},
                },
                {
                    "task_id": "sentiment_analysis",
                    "agent": "sentiment_analysis",
                    "priority": "P1",
                    "parameters": {},
                },
            ],
            "timeouts": {"task_timeout_s": 0.05, "stage_timeout_s": 0.1},
            "results": {},
            "approved_agents": ["fundamental_analysis", "sentiment_analysis"],
            "required_agents": [],
        }
    )

    assert "sentiment_analysis" in result["results"]
    assert "fundamental_analysis" not in result["results"]
