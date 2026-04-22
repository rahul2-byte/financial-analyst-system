from __future__ import annotations

import pytest

from agents.financial.research.research_execution_node import research_execution_node


@pytest.mark.asyncio
async def test_research_execution_audit_includes_stage_diagnostics() -> None:
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

    audit = result["data"]["audit"]
    summary = audit["decision_summary"]
    assert "stage_diagnostics" in summary
    assert isinstance(summary["stage_diagnostics"], list)
    assert len(summary["stage_diagnostics"]) >= 1
