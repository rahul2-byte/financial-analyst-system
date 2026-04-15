from __future__ import annotations

import pytest

from app.core.intent_classifier import IntentClassificationResult
from app.core.orchestrator import PipelineOrchestrator
from app.core.query_scope import normalize_research_scope


def test_normalize_research_scope_expands_broad_deep_analysis_queries() -> None:
    query = "Analyze HDFC Bank for last one year with full deep analysis"

    normalized = normalize_research_scope(query)

    assert normalized.startswith(query)
    assert "Time horizon: 1 year" in normalized
    assert "fundamentals" in normalized.lower()
    assert "risks" in normalized.lower()


def test_normalize_research_scope_preserves_specific_queries() -> None:
    query = "Analyze HDFC Bank asset quality trends and deposit growth over the last 2 quarters"

    assert normalize_research_scope(query) == query


@pytest.mark.asyncio
async def test_orchestrator_uses_scope_normalized_query_for_graph_state(monkeypatch) -> None:
    async def _stub_classifier(_query: str, _history):
        return IntentClassificationResult(
            label="financial",
            is_financial_request=True,
            confidence=0.95,
            assistant_response="",
        )

    captured: dict[str, object] = {}

    def _build_initial_graph_state(*, user_query, conversation_history):
        captured["user_query"] = user_query
        captured["conversation_history"] = conversation_history
        return {"user_query": user_query}

    class _StubSessionLogger:
        def log_step(self, *_args, **_kwargs):
            return None

        def log_error(self, *_args, **_kwargs):
            return None

    class _StubGraph:
        async def astream_events(self, *_args, **_kwargs):
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {"final_output": "done"}},
            }

    monkeypatch.setattr("app.core.orchestrator.classify_query_intent", _stub_classifier)
    monkeypatch.setattr("app.core.orchestrator.build_initial_graph_state", _build_initial_graph_state)
    monkeypatch.setattr(
        "app.core.orchestrator.SessionLogger.get_logger",
        lambda _query: _StubSessionLogger(),
    )
    monkeypatch.setattr(
        "app.core.orchestrator.langfuse_context.update_current_trace",
        lambda **_kwargs: None,
    )

    orchestrator = PipelineOrchestrator()
    orchestrator.research_graph = _StubGraph()

    events = [
        event
        async for event in orchestrator.execute_query(
            "Analyze HDFC Bank for last one year with full deep analysis"
        )
    ]

    assert events[-1].type == "done"
    assert isinstance(captured["user_query"], str)
    assert "Time horizon: 1 year" in captured["user_query"]
