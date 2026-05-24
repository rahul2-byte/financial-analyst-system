import pytest

from agents.financial.research.research_execution_node import research_execution_node


@pytest.mark.asyncio
async def test_research_execution_blocks_when_required_agent_payload_missing(
    monkeypatch,
) -> None:
    async def _fake_fundamental(_state, _resources):
        return {"errors": ["tool unavailable"]}

    import agents.financial.research.research_execution_node as node_module

    monkeypatch.setitem(
        node_module.AGENT_NODE_MAP, "fundamental_analysis", _fake_fundamental
    )

    result = await research_execution_node(
        {
            "tasks": [
                {
                    "task_id": "fundamental_analysis",
                    "agent": "fundamental_analysis",
                    "priority": "P0",
                    "objective": "Assess fundamentals",
                    "research_question": "Assess fundamentals for the company",
                    "structured_requirements": {"datasets": ["fundamentals"]},
                    "qualitative_requirements": {"enabled": False},
                    "parameters": {},
                }
            ],
            "approved_agents": ["fundamental_analysis"],
            "timeouts": {"task_timeout_s": 1.0, "stage_timeout_s": 1.0},
        }
    )

    assert result["status"] == "failure"
    assert any("required agent" in error.lower() for error in result["errors"])
    assert result["next_action"] == "terminate_failure"


@pytest.mark.asyncio
async def test_research_execution_blocks_when_required_agent_payload_is_none(
    monkeypatch,
) -> None:
    async def _fake_fundamental(_state, _resources):
        return None

    import agents.financial.research.research_execution_node as node_module

    monkeypatch.setitem(
        node_module.AGENT_NODE_MAP, "fundamental_analysis", _fake_fundamental
    )

    result = await research_execution_node(
        {
            "results": {"fundamental_analysis": None},
            "tasks": [
                {
                    "task_id": "fundamental_analysis",
                    "agent": "fundamental_analysis",
                    "priority": "P0",
                    "objective": "Assess fundamentals",
                    "research_question": "Assess fundamentals for the company",
                    "structured_requirements": {"datasets": ["fundamentals"]},
                    "qualitative_requirements": {"enabled": False},
                    "parameters": {},
                }
            ],
            "approved_agents": ["fundamental_analysis"],
            "timeouts": {"task_timeout_s": 1.0, "stage_timeout_s": 1.0},
        }
    )

    assert result["status"] == "failure"
    assert any("no result" in error.lower() for error in result["errors"])
    assert result["next_action"] == "terminate_failure"
