from __future__ import annotations

from typing import Any

import pytest

from app.core.graph.graph_state import build_initial_graph_state
from app.core.intent_classifier import IntentClassificationResult
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
async def test_orchestrator_uses_scope_normalized_query_for_graph_state(
    monkeypatch,
) -> None:
    import importlib

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

        def log_trace(self, *_args, **_kwargs):
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
    monkeypatch.setattr(
        "app.core.orchestrator.build_initial_graph_state", _build_initial_graph_state
    )
    monkeypatch.setattr(
        "app.core.orchestrator.SessionLogger.get_logger",
        lambda _query: _StubSessionLogger(),
    )
    monkeypatch.setattr(
        "app.core.orchestrator.langfuse_context.update_current_trace",
        lambda **_kwargs: None,
    )

    orchestrator_mod = importlib.import_module("app.core.orchestrator")
    orchestrator = orchestrator_mod.PipelineOrchestrator()
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


@pytest.mark.asyncio
async def test_orchestrator_logs_node_outputs_to_session_audit(monkeypatch) -> None:
    import importlib

    async def _stub_classifier(_query: str, _history):
        return IntentClassificationResult(
            label="financial",
            is_financial_request=True,
            confidence=0.95,
            assistant_response="",
        )

    class _RecordingSessionLogger:
        def __init__(self) -> None:
            self.steps: list[tuple[str, str, Any, Any]] = []
            self.traces: list[tuple[str, Any]] = []

        def log_step(self, step_name, explanation, parameters=None, data=None):
            self.steps.append((step_name, explanation, parameters, data))

        def log_trace(self, event_name, payload):
            self.traces.append((event_name, payload))

        def log_error(self, *_args, **_kwargs):
            return None

    session_logger = _RecordingSessionLogger()

    class _StubGraph:
        async def astream_events(self, *_args, **_kwargs):
            yield {"event": "on_node_start", "name": "goal_node"}
            yield {
                "event": "on_node_end",
                "name": "goal_node",
                "data": {
                    "output": {
                        "status": "success",
                        "next_action": "run_data_check",
                        "goal": {"ticker": "HDFCBANK"},
                        "data": {
                            "audit": {
                                "node": "goal_node",
                                "ticker": "HDFCBANK",
                                "status": "success",
                            }
                        },
                    }
                },
            }
            yield {"event": "on_node_start", "name": "research_plan_node"}
            yield {
                "event": "on_node_end",
                "name": "research_plan_node",
                "data": {
                    "input": {
                        "goal": {},
                        "timeframe": "",
                        "iteration_count": 0,
                        "router_decision": "",
                    },
                    "output": {
                        "status": "success",
                        "next_action": "run_research_context",
                        "goal": {"ticker": "HDFCBANK"},
                        "timeframe": "1y",
                        "iteration_count": 2,
                        "router_decision": "run_research_plan",
                        "tasks": [{"task_id": "fundamental_analysis"}],
                    },
                },
            }
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {
                    "output": {
                        "status": "success",
                        "next_action": "complete",
                        "final_output": "done",
                        "data": {
                            "audit": {
                                "node": "pipeline",
                                "ticker": "HDFCBANK",
                                "status": "success",
                            }
                        },
                    }
                },
            }

    monkeypatch.setattr("app.core.orchestrator.classify_query_intent", _stub_classifier)
    monkeypatch.setattr(
        "app.core.orchestrator.build_initial_graph_state",
        lambda **kwargs: build_initial_graph_state(**kwargs),
    )
    monkeypatch.setattr(
        "app.core.orchestrator.SessionLogger.get_logger",
        lambda _query: session_logger,
    )
    monkeypatch.setattr(
        "app.core.orchestrator.langfuse_context.update_current_trace",
        lambda **_kwargs: None,
    )

    orchestrator_mod = importlib.import_module("app.core.orchestrator")
    orchestrator = orchestrator_mod.PipelineOrchestrator()
    orchestrator.research_graph = _StubGraph()

    events = [
        event
        async for event in orchestrator.execute_query(
            "Analyze HDFC Bank for last one year with full deep analysis"
        )
    ]

    assert events[-1].type == "done"
    step_names = [step[0] for step in session_logger.steps]
    assert "RECEIVE_QUERY" in step_names
    assert "NODE_GOAL_NODE" in step_names
    assert "NODE_RESEARCH_PLAN_NODE" in step_names
    goal_step = next(
        step for step in session_logger.steps if step[0] == "NODE_GOAL_NODE"
    )
    assert goal_step[3]["audit"]["node"] == "goal_node"
    assert goal_step[3]["audit"]["ticker"] == "HDFCBANK"
    research_plan_step = next(
        step for step in session_logger.steps if step[0] == "NODE_RESEARCH_PLAN_NODE"
    )
    assert research_plan_step[3]["audit"]["node"] == "research_plan_node"
    assert research_plan_step[3]["audit"]["ticker"] == "HDFCBANK"
    assert research_plan_step[3]["audit"]["timeframe"] == "1y"
    assert research_plan_step[3]["audit"]["iteration_count"] == 2
    assert research_plan_step[3]["audit"]["router_decision"] == "run_research_plan"
    pipeline_step = next(
        step for step in session_logger.steps if step[0] == "PIPELINE_RESULT"
    )
    assert pipeline_step[3]["audit"]["node"] == "pipeline"
    assert pipeline_step[3]["audit"]["status"] == "success"
    assert any(name == "node_start" for name, _ in session_logger.traces)
    assert any(name == "node_end" for name, _ in session_logger.traces)
