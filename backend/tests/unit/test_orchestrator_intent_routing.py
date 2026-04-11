import pytest

from app.core.intent_classifier import IntentClassificationResult
import app.core.orchestrator
import importlib

importlib.reload(app.core.orchestrator)
from app.core.orchestrator import PipelineOrchestrator


class _FailIfCalledGraph:
    def __init__(self) -> None:
        self.called = False

    async def astream_events(self, *_args, **_kwargs):
        self.called = True
        raise AssertionError("research graph should not run")
        yield  # pragma: no cover


class _StubGraph:
    def __init__(self) -> None:
        self.called = False

    async def astream_events(self, *_args, **_kwargs):
        self.called = True
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {"final_output": {"status": "success"}}},
        }


def _patch_classifier(monkeypatch, label: str, response_text: str):
    async def _stub_classifier(_query: str, _history):
        return IntentClassificationResult(
            label=label,
            is_financial_request=(label == "financial"),
            confidence=0.95,
            assistant_response=response_text,
        )

    monkeypatch.setattr("app.core.orchestrator.classify_query_intent", _stub_classifier)


@pytest.mark.asyncio
async def test_financial_query_flows_to_graph_execution(monkeypatch) -> None:
    _patch_classifier(monkeypatch, "financial", "")

    orchestrator = app.core.orchestrator.PipelineOrchestrator()
    fake_graph = _StubGraph()
    orchestrator.research_graph = fake_graph

    events = [event async for event in orchestrator.execute_query("Analyze AAPL")]

    assert fake_graph.called is True
    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_non_financial_query_short_circuits_before_graph(monkeypatch) -> None:
    _patch_classifier(
        monkeypatch,
        "non_financial",
        "I focus on finance-related analysis.",
    )

    orchestrator = app.core.orchestrator.PipelineOrchestrator()
    fake_graph = _FailIfCalledGraph()
    orchestrator.research_graph = fake_graph

    events = [event async for event in orchestrator.execute_query("Write me a recipe")]

    assert fake_graph.called is False
    assert events[-1].type == "done"
    text = "".join(
        event.content or "" for event in events if event.type == "text_delta"
    )
    assert "finance" in text.lower()


@pytest.mark.asyncio
async def test_classifier_exception_fails_closed(monkeypatch) -> None:
    async def _boom(_query: str, _history):
        print("BOOM WAS CALLED!!!")
        raise RuntimeError("classifier offline")

    monkeypatch.setattr("app.core.orchestrator.classify_query_intent", _boom)

    orchestrator = app.core.orchestrator.PipelineOrchestrator()
    fake_graph = _FailIfCalledGraph()
    orchestrator.research_graph = fake_graph

    events = [event async for event in orchestrator.execute_query("Analyze AAPL")]

    assert fake_graph.called is False
    assert events[-1].type == "done"
    text = "".join(
        event.content or "" for event in events if event.type == "text_delta"
    )
    assert "finance" in text.lower()
