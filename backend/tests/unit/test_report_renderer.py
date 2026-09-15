import pytest
from app.core.model_stream import capture_public_tokens, get_public_token_sink
from app.core.node_resources import resources
from app.core.report_renderer import generate_narrative_report


class _StubLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _StubLLMService:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0
        self.last_messages: list[object] = []

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


@pytest.mark.asyncio
async def test_report_renderer_publishes_only_its_narrative_tokens(monkeypatch) -> None:
    class _StreamingStub:
        async def generate_message(self, messages, model, tools=None):
            sink = get_public_token_sink()
            assert sink is not None
            await sink("Narrative")
            return _StubLLMResponse("Narrative")

    received: list[str] = []

    async def sink(token: str) -> None:
        received.append(token)

    monkeypatch.setattr(resources, "_llm_service", _StreamingStub())

    with capture_public_tokens(sink):
        report = await generate_narrative_report(
            {"user_query": "Analyze AAPL", "results": {"synthesis": {}}},
            resources,
        )

    assert report == "Narrative"
    assert received == ["Narrative"]


@pytest.mark.asyncio
async def test_report_renderer_discloses_partial_evidence(monkeypatch) -> None:
    stub = _StubLLMService("Narrative")
    monkeypatch.setattr(resources, "_llm_service", stub)

    report = await generate_narrative_report(
        {
            "user_query": "Analyze AAPL",
            "data_status": {
                "fundamentals": {"status": "available"},
                "ohlcv": {
                    "status": "unavailable",
                    "error_code": "HTTP_403",
                },
            },
            "results": {"synthesis": {}},
        },
        resources,
    )

    assert report.startswith("> [!WARNING]")
    assert "ohlcv" in report
    assert "HTTP_403" in report
