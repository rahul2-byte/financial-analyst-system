from __future__ import annotations

import importlib

import pytest

from app.core.intent_classifier import IntentClassificationResult


@pytest.mark.asyncio
async def test_orchestrator_logs_loop_warning_for_repeated_transition(
    monkeypatch,
) -> None:
    async def _stub_classifier(_query: str, _history):
        return IntentClassificationResult(
            label="financial",
            is_financial_request=True,
            confidence=0.95,
            assistant_response="",
        )

    class _RecordingSessionLogger:
        def __init__(self) -> None:
            self.traces: list[tuple[str, dict]] = []

        def log_step(self, *_args, **_kwargs):
            return None

        def log_trace(self, event_name, payload):
            self.traces.append((event_name, payload))

        def log_error(self, *_args, **_kwargs):
            return None

    session_logger = _RecordingSessionLogger()

    class _StubGraph:
        async def astream_events(self, *_args, **_kwargs):
            for _ in range(4):
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
                            "next_action": "run_research_plan",
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

    _ = [
        event
        async for event in orchestrator.execute_query(
            "Analyze HDFC Bank for last one year with full deep analysis"
        )
    ]

    loop_warnings = [
        payload for name, payload in session_logger.traces if name == "loop_warning"
    ]
    assert loop_warnings
    latest_warning = loop_warnings[-1]
    assert latest_warning["reason"] == "repeated_transition"
    assert "transition" in latest_warning
    assert "node_call_counts" in latest_warning
    assert "transition_counts" in latest_warning
