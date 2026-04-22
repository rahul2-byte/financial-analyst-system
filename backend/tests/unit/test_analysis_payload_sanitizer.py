import json

import pytest

from agents.financial.analysis.fundamental import fundamental_analysis_node
from agents.financial.analysis.payload_sanitizer import (
    drop_findings_without_evidence_ids,
)
from app.core.node_resources import resources


class _StubLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content
        self.tool_calls = None


class _StaticLLMService:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    async def generate_message(self, messages, model, response_format=None):
        del messages, model, response_format
        return _StubLLMResponse(json.dumps(self.payload))


def test_drop_findings_without_evidence_ids_removes_invalid_findings() -> None:
    payload = {
        "status": "ok",
        "findings": [
            {
                "finding_id": "f1",
                "dimension": "profitability",
                "summary": "Valid finding",
                "evidence_ids": ["ev1"],
                "unresolved": False,
            },
            {
                "finding_id": "f2",
                "dimension": "valuation",
                "summary": "Missing links",
                "evidence_ids": [],
                "unresolved": False,
            },
            {
                "finding_id": "f3",
                "dimension": "balance_sheet",
                "summary": "Missing field",
                "unresolved": False,
            },
        ],
        "claims": [],
        "confidence": 0.7,
    }

    sanitized = drop_findings_without_evidence_ids(payload)

    assert [finding["finding_id"] for finding in sanitized["findings"]] == ["f1"]
    assert sanitized["claims"] == []
    assert sanitized["confidence"] == 0.7


@pytest.mark.asyncio
async def test_fundamental_analysis_node_drops_findings_without_evidence_ids(
    monkeypatch,
) -> None:
    previous = resources._llm_service
    monkeypatch.setattr(
        resources,
        "_llm_service",
        _StaticLLMService(
            {
                "status": "ok",
                "findings": [
                    {
                        "finding_id": "f1",
                        "dimension": "profitability",
                        "summary": "Supported finding",
                        "evidence_ids": ["ev1"],
                        "unresolved": False,
                    },
                    {
                        "finding_id": "f2",
                        "dimension": "valuation",
                        "summary": "Unsupported finding",
                        "evidence_ids": [],
                        "unresolved": False,
                    },
                ],
                "claims": [],
                "risks": [],
                "missing_evidence": [],
                "confidence": 0.85,
            }
        ),
    )
    try:
        result = await fundamental_analysis_node(
            {
                "current_step": {
                    "parameters": {
                        "ticker": "AAPL",
                        "raw_data": {"marketCap": 100, "currentPrice": 10},
                    }
                }
            },
            resources,
        )
    finally:
        monkeypatch.setattr(resources, "_llm_service", previous)

    payload = result["agent_outputs"]["fundamental_analysis"]
    assert payload["status"] == "ok"
    assert [finding["finding_id"] for finding in payload["findings"]] == ["f1"]
