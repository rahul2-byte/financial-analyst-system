import pytest

from app.core.intent_classifier import IntentClassificationResult
from app.core.orchestrator import PipelineOrchestrator


class _EventSequenceGraph:
    def __init__(self, events: list[object]) -> None:
        self.events = events

    async def astream_events(self, *_args, **_kwargs):
        for event in self.events:
            yield event


def _patch_financial_classifier(monkeypatch):
    async def _stub_classifier(_query: str, _history):
        return IntentClassificationResult(
            label="financial",
            is_financial_request=True,
            confidence=0.95,
            assistant_response="",
        )

    monkeypatch.setattr("app.core.orchestrator.classify_query_intent", _stub_classifier)


@pytest.mark.asyncio
async def test_skips_malformed_events_and_keeps_processing(monkeypatch) -> None:
    _patch_financial_classifier(monkeypatch)

    orchestrator = PipelineOrchestrator()
    orchestrator.research_graph = _EventSequenceGraph(
        [
            {"name": "missing_event_key"},
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {"final_output": {"status": "success"}}},
            },
        ]
    )

    events = [event async for event in orchestrator.execute_query("Analyze AAPL")]

    assert events[-1].type == "done"
    assert not any(event.type == "error" for event in events)


@pytest.mark.asyncio
async def test_does_not_duplicate_when_tokens_already_streamed(monkeypatch) -> None:
    _patch_financial_classifier(monkeypatch)

    orchestrator = PipelineOrchestrator()

    class _Chunk:
        def __init__(self, content: str) -> None:
            self.content = content

    orchestrator.research_graph = _EventSequenceGraph(
        [
            {
                "event": "on_chat_model_stream",
                "data": {"chunk": _Chunk("TokenStream")},
            },
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {"final_output": "FinalFallback"}},
            },
        ]
    )

    events = [event async for event in orchestrator.execute_query("Analyze AAPL")]
    text_payloads = [event.content for event in events if event.type == "text_delta"]

    assert text_payloads == ["TokenStream"]
    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_prefers_final_report_over_final_output(monkeypatch) -> None:
    _patch_financial_classifier(monkeypatch)

    orchestrator = PipelineOrchestrator()
    orchestrator.research_graph = _EventSequenceGraph(
        [
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {
                    "output": {
                        "final_report": "# Executive Summary\n\nNarrative report",
                        "final_output": {"status": "success", "decision": "watchlist"},
                    }
                },
            }
        ]
    )

    events = [event async for event in orchestrator.execute_query("Analyze AAPL")]
    text_payloads = [event.content for event in events if event.type == "text_delta"]
    payload_events = [
        event.payload for event in events if event.type == "final_payload"
    ]

    assert text_payloads == ["# Executive Summary\n\nNarrative report"]
    assert payload_events == [{"status": "success", "decision": "watchlist"}]
    assert events[-1].type == "done"
