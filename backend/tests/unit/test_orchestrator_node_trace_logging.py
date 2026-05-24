from __future__ import annotations

import importlib

import pytest

from app.core.intent_classifier import IntentClassificationResult


@pytest.mark.asyncio
async def test_orchestrator_emits_node_start_and_end_traces(monkeypatch) -> None:
    async def _stub_classifier(_query: str, _history):
        return IntentClassificationResult(
            label="financial",
            is_financial_request=True,
            confidence=0.95,
            assistant_response="",
        )

    class _RecordingSessionLogger:
        def __init__(self) -> None:
            self.steps: list[tuple[str, str, object, object]] = []
            self.traces: list[tuple[str, dict]] = []

        def log_step(self, step_name, explanation, parameters=None, data=None):
            self.steps.append((step_name, explanation, parameters, data))

        def log_trace(self, event_name, payload):
            self.traces.append((event_name, payload))

        def log_error(self, *_args, **_kwargs):
            return None

    session_logger = _RecordingSessionLogger()

    class _StubGraph:
        async def astream_events(self, *_args, **_kwargs):
            yield {
                "event": "on_node_start",
                "name": "router_node",
                "data": {"input": {}},
            }
            yield {
                "event": "on_node_end",
                "name": "router_node",
                "data": {
                    "output": {
                        "status": "success",
                        "next_action": "run_goal",
                        "errors": [],
                    }
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
                        "data": {},
                        "errors": [],
                    }
                },
            }

    monkeypatch.setattr("app.core.orchestrator.classify_query_intent", _stub_classifier)
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

    trace_names = [name for name, _ in session_logger.traces]
    assert "node_start" in trace_names
    assert "node_end" in trace_names
    assert "pipeline_loop_snapshot" in trace_names

    node_start_payload = next(
        payload for name, payload in session_logger.traces if name == "node_start"
    )
    assert node_start_payload["node"] == "router_node"
    assert node_start_payload["node_call_index"] == 1
    assert "state_summary" in node_start_payload

    node_end_payload = next(
        payload for name, payload in session_logger.traces if name == "node_end"
    )
    assert node_end_payload["node"] == "router_node"
    assert node_end_payload["status"] == "success"
    assert node_end_payload["next_action"] == "run_goal"
    assert "duration_ms" in node_end_payload


@pytest.mark.asyncio
async def test_orchestrator_emits_node_error_trace(monkeypatch) -> None:
    async def _stub_classifier(_query: str, _history):
        return IntentClassificationResult(
            label="financial",
            is_financial_request=True,
            confidence=0.95,
            assistant_response="",
        )

    class _RecordingSessionLogger:
        def __init__(self) -> None:
            self.steps: list[tuple[str, str, object, object]] = []
            self.traces: list[tuple[str, dict]] = []

        def log_step(self, step_name, explanation, parameters=None, data=None):
            self.steps.append((step_name, explanation, parameters, data))

        def log_trace(self, event_name, payload):
            self.traces.append((event_name, payload))

        def log_error(self, *_args, **_kwargs):
            return None

    session_logger = _RecordingSessionLogger()

    class _StubGraph:
        async def astream_events(self, *_args, **_kwargs):
            yield {
                "event": "on_node_start",
                "name": "router_node",
                "data": {"input": {}},
            }
            yield {
                "event": "on_node_error",
                "name": "router_node",
                "data": {"error": "router exploded", "input": {"iteration_count": 1}},
            }
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {
                    "output": {
                        "status": "failure",
                        "next_action": "terminate_failure",
                        "final_output": "done",
                        "data": {},
                        "errors": ["router exploded"],
                    }
                },
            }

    monkeypatch.setattr("app.core.orchestrator.classify_query_intent", _stub_classifier)
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
    trace_names = [name for name, _ in session_logger.traces]
    assert "node_error" in trace_names
    node_error_payload = next(
        payload for name, payload in session_logger.traces if name == "node_error"
    )
    assert node_error_payload["node"] == "router_node"
    assert node_error_payload["error"] == "router exploded"
    assert node_error_payload["node_call_index"] == 1


@pytest.mark.asyncio
async def test_orchestrator_maps_chain_events_to_node_traces(monkeypatch) -> None:
    async def _stub_classifier(_query: str, _history):
        return IntentClassificationResult(
            label="financial",
            is_financial_request=True,
            confidence=0.95,
            assistant_response="",
        )

    class _RecordingSessionLogger:
        def __init__(self) -> None:
            self.steps: list[tuple[str, str, object, object]] = []
            self.traces: list[tuple[str, dict]] = []

        def log_step(self, step_name, explanation, parameters=None, data=None):
            self.steps.append((step_name, explanation, parameters, data))

        def log_trace(self, event_name, payload):
            self.traces.append((event_name, payload))

        def log_error(self, *_args, **_kwargs):
            return None

    session_logger = _RecordingSessionLogger()

    class _StubGraph:
        async def astream_events(self, *_args, **_kwargs):
            yield {
                "event": "on_chain_start",
                "name": "LangGraph",
                "data": {"input": {}},
            }
            yield {
                "event": "on_chain_start",
                "name": "router_node",
                "data": {"input": {"iteration_count": 1}},
            }
            yield {
                "event": "on_chain_end",
                "name": "router_node",
                "data": {
                    "output": {
                        "status": "success",
                        "next_action": "run_goal",
                        "errors": [],
                    }
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
                        "data": {},
                        "errors": [],
                    }
                },
            }

    monkeypatch.setattr("app.core.orchestrator.classify_query_intent", _stub_classifier)
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
    trace_names = [name for name, _ in session_logger.traces]
    assert "pipeline_chain_start" in trace_names
    assert "node_start" in trace_names
    assert "node_end" in trace_names


@pytest.mark.asyncio
async def test_orchestrator_emits_opik_node_spans(monkeypatch):
    import app.core.observability as obs
    from app.core.intent_classifier import IntentClassificationResult
    
    metadata_calls = []
    
    class MockOpikContext:
        def update_current_span(self, name=None, metadata=None):
            if metadata:
                metadata_calls.append(metadata)
        def update_current_trace(self, input=None, tags=None, metadata=None, **kwargs):
            pass
            
    monkeypatch.setattr(obs, "opik_context", MockOpikContext())
    monkeypatch.setattr(obs, "observe", lambda **kw: lambda f: f)
    
    async def _stub_classifier(_query: str, _history):
        return IntentClassificationResult(
            label="financial",
            is_financial_request=True,
            confidence=0.95,
            assistant_response="",
        )

    class _StubGraph:
        async def astream_events(self, *_args, **_kwargs):
            yield {
                "event": "on_node_start",
                "name": "router_node",
                "data": {"input": {}},
            }
            yield {
                "event": "on_node_end",
                "name": "router_node",
                "data": {
                    "output": {
                        "status": "success",
                        "next_action": "run_goal",
                        "errors": [],
                    }
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
                        "data": {},
                        "errors": [],
                    }
                },
            }

    monkeypatch.setattr("app.core.orchestrator.classify_query_intent", _stub_classifier)
    monkeypatch.setattr("app.core.orchestrator.SessionLogger.get_logger", lambda _q: type("StubLogger", (), {"log_step": lambda *a, **k: None, "log_trace": lambda *a, **k: None, "log_error": lambda *a, **k: None})())
    
    importlib = __import__("importlib")
    orchestrator_mod = importlib.import_module("app.core.orchestrator")
    # Patch the opik_context that orchestrator_mod imported
    monkeypatch.setattr(orchestrator_mod, "opik_context", MockOpikContext(), raising=False)

    orchestrator = orchestrator_mod.PipelineOrchestrator()
    orchestrator.research_graph = _StubGraph()

    _events = [
        event
        async for event in orchestrator.execute_query(
            "Analyze AAPL"
        )
    ]

    assert len(metadata_calls) > 0
    # There should be an update with duration_ms from on_node_end
    assert any("duration_ms" in m for m in metadata_calls)
