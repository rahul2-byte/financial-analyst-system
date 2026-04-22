import pytest

from app.core.node_resources import resources
from app.core.report_renderer import generate_narrative_report


class _StubLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _StubLLMService:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0
        self.last_messages = []

    async def generate_message(self, messages, model, tools=None):
        self.calls += 1
        self.last_messages = messages
        return _StubLLMResponse(self.content)


@pytest.mark.asyncio
async def test_report_renderer_generates_narrative(monkeypatch) -> None:
    stub = _StubLLMService("# Executive Summary\n\nNarrative report")
    monkeypatch.setattr(resources, "_llm_service", stub)

    state = {
        "user_query": "Analyze AAPL",
        "results": {
            "synthesis": {
                "decision": "watchlist",
                "key_drivers": ["Strong fundamentals"],
                "risks": ["Market volatility"],
            },
            "fundamental_analysis": {"summary": "Validated fundamentals"},
        },
    }

    report = await generate_narrative_report(state, resources)

    assert report == "# Executive Summary\n\nNarrative report"
    assert stub.calls == 1


@pytest.mark.asyncio
async def test_report_renderer_prepends_low_confidence_disclaimer(monkeypatch) -> None:
    stub = _StubLLMService("# Executive Summary\n\nNarrative report")
    monkeypatch.setattr(resources, "_llm_service", stub)

    report = await generate_narrative_report(
        {"user_query": "Analyze AAPL", "results": {"synthesis": {}}},
        resources,
        terminal_output={"status": "low_confidence", "reasoning": "Evidence was weak."},
        is_low_confidence=True,
        reason="Evidence was weak.",
    )

    assert report.startswith("> [!WARNING]")
    assert "Evidence was weak." in report
    assert "Narrative report" in report
