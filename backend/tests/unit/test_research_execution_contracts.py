import pytest

from agents.financial.research.research_execution_node import research_execution_node


@pytest.mark.asyncio
async def test_research_execution_runs_dependency_stage_before_contrarian(monkeypatch):
    call_order: list[str] = []

    async def _fundamental(state, _resources):
        call_order.append("fundamental_analysis")
        return {
            "agent_outputs": {
                "fundamental_analysis": {
                    "agent": "fundamental_analysis",
                    "status": "ok",
                    "findings": [
                        {
                            "finding_id": "f1",
                            "dimension": "dim",
                            "summary": "base finding",
                            "evidence_ids": ["e1"],
                            "unresolved": False,
                        }
                    ],
                    "claims": [
                        {
                            "claim_id": "c1",
                            "text": "base claim",
                            "importance": "major",
                            "evidence_refs": ["e1"],
                            "contradicted_by": [],
                        }
                    ],
                    "confidence": 0.9,
                }
            },
            "errors": [],
        }

    async def _contrarian(state, _resources):
        call_order.append("contrarian_analysis")
        dependency_results = state["current_step"]["parameters"]["execution_input"][
            "evidence_bundle"
        ]["dependency_results"]
        return {
            "agent_outputs": {
                "contrarian_analysis": {
                    "agent": "contrarian_analysis",
                    "status": "ok",
                    "findings": dependency_results["fundamental_analysis"]["findings"],
                    "claims": dependency_results["fundamental_analysis"]["claims"],
                    "confidence": 0.8,
                }
            },
            "errors": [],
        }

    import agents.financial.research.research_execution_node as node_module

    monkeypatch.setitem(
        node_module.AGENT_NODE_MAP, "fundamental_analysis", _fundamental
    )
    monkeypatch.setitem(node_module.AGENT_NODE_MAP, "contrarian_analysis", _contrarian)

    state = {
        "tasks": [
            {
                "task_id": "fundamental_analysis",
                "agent": "fundamental_analysis",
                "priority": "P0",
                "objective": "Base",
                "research_question": "Base question",
                "structured_requirements": {"datasets": ["fundamentals"]},
                "qualitative_requirements": {"enabled": False},
                "parameters": {},
            },
            {
                "task_id": "contrarian_analysis",
                "agent": "contrarian_analysis",
                "priority": "P2",
                "objective": "Counter",
                "research_question": "Counter question",
                "depends_on": ["fundamental_analysis"],
                "structured_requirements": {"datasets": []},
                "qualitative_requirements": {"enabled": False},
                "parameters": {},
            },
        ],
        "task_contexts": {
            "fundamental_analysis": {
                "agent": "fundamental_analysis",
                "objective": "Base",
                "research_question": "Base question",
                "evidence_bundle": {
                    "structured_inputs": {"fundamentals": {"marketCap": 1}}
                },
            },
            "contrarian_analysis": {
                "agent": "contrarian_analysis",
                "objective": "Counter",
                "research_question": "Counter question",
                "evidence_bundle": {},
            },
        },
        "approved_agents": ["fundamental_analysis", "contrarian_analysis"],
        "timeouts": {"task_timeout_s": 1.0, "stage_timeout_s": 1.0},
    }

    result = await research_execution_node(state)

    assert result["status"] == "success"
    assert call_order == ["fundamental_analysis", "contrarian_analysis"]
    assert len(result["results"]["contrarian_analysis"]["findings"]) == 1
    assert (
        result["results"]["contrarian_analysis"]["findings"][0]["summary"]
        == "base finding"
    )


@pytest.mark.asyncio
async def test_research_execution_audit_logs_outcomes(monkeypatch) -> None:
    async def _fundamental(state, _resources):
        return {
            "agent_outputs": {
                "fundamental_analysis": {
                    "agent": "fundamental_analysis",
                    "status": "ok",
                    "findings": [
                        {
                            "finding_id": "f1",
                            "dimension": "dim",
                            "summary": "base finding",
                            "evidence_ids": ["e1"],
                            "unresolved": False,
                        }
                    ],
                    "claims": [
                        {
                            "claim_id": "c1",
                            "text": "base claim",
                            "importance": "major",
                            "evidence_refs": ["e1"],
                            "contradicted_by": [],
                        }
                    ],
                    "confidence": 0.9,
                }
            },
            "errors": [],
        }

    import agents.financial.research.research_execution_node as node_module

    monkeypatch.setitem(
        node_module.AGENT_NODE_MAP, "fundamental_analysis", _fundamental
    )

    state = {
        "goal": {"ticker": "AAPL"},
        "tasks": [
            {
                "task_id": "fundamental_analysis",
                "agent": "fundamental_analysis",
                "priority": "P0",
                "objective": "Base",
                "research_question": "Base question",
                "structured_requirements": {"datasets": []},
                "qualitative_requirements": {"enabled": False},
                "parameters": {},
            },
        ],
        "task_contexts": {
            "fundamental_analysis": {
                "agent": "fundamental_analysis",
                "objective": "Base",
                "research_question": "Base question",
                "evidence_bundle": {"structured_inputs": {}},
            },
        },
        "approved_agents": ["fundamental_analysis"],
        "timeouts": {"task_timeout_s": 1.0, "stage_timeout_s": 1.0},
    }

    result = await research_execution_node(state)

    audit = result["data"]["audit"]
    assert audit["node"] == "research_execution_node"
    assert audit["ticker"] == "AAPL"

    summary = audit["decision_summary"]
    assert summary["stages_executed"] == 1
    assert "fundamental_analysis" in summary["agent_outcomes"]
    assert summary["agent_outcomes"]["fundamental_analysis"]["status"] == "ok"
    assert summary["agent_outcomes"]["fundamental_analysis"]["has_errors"] is False
    assert (
        "1 findings, 1 claims"
        in summary["agent_outcomes"]["fundamental_analysis"]["result_preview"]
    )
