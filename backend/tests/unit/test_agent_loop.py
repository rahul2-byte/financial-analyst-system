from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from app.core.agent_loop import AgentLoop, AgentLoopConfig
from app.core.skills import SkillRegistry
from app.models.request_models import Message


class FakeModel:
    def __init__(self, responses: list[list[dict]]) -> None:
        self.responses = iter(responses)
        self.calls: list[list[Message]] = []
        self.request_kwargs: list[dict] = []

    def generate_stream(self, messages: list[Message], model: str, **kwargs):
        del model
        self.calls.append(list(messages))
        self.request_kwargs.append(kwargs)
        response = next(self.responses)

        async def stream():
            for item in response:
                yield item

        return stream()


class FakeTools:
    def definitions(self) -> list[dict]:
        return [{"type": "function", "function": {"name": "data:lookup"}}]

    async def execute(self, name: str, arguments: dict) -> dict:
        assert name == "data:lookup"
        return {"success": True, "data": {"ticker": arguments["ticker"]}}


class FailedTools:
    def definitions(self) -> list[dict]:
        return [
            {"type": "function", "function": {"name": "analysis:run_technical_scan"}}
        ]

    async def execute(self, name: str, arguments: dict) -> dict:
        return {"success": False, "error": "No OHLCV data provided"}


class InterruptedModel:
    def generate_stream(self, messages: list[Message], model: str, **kwargs):
        del messages, model, kwargs

        async def stream():
            yield {"event": "token", "data": "A useful partial report. " * 12}
            raise RuntimeError("provider stream disconnected")

        return stream()


class ReportTools:
    def definitions(self) -> list[dict]:
        return [{"type": "function", "function": {"name": "data:fetch_stock_data"}}]

    async def execute(self, name: str, arguments: dict) -> dict:
        del name, arguments
        return {
            "success": True,
            "data": {"latest": {"close": 123.4}},
            "provenance": {
                "source": "fixture",
                "dataset": "prices",
                "instrument": "ABC.NS",
                "observed_at": "2026-09-18T00:00:00+00:00",
                "ingested_at": "2026-09-18T00:01:00+00:00",
                "version": "fixture-1",
                "quality_status": "verified",
            },
        }


def test_loop_streams_answer_without_reusing_previous_response() -> None:
    model = FakeModel([[{"event": "token", "data": "first"}]])
    loop = AgentLoop(model, FakeTools())

    events = asyncio.run(_collect(loop, [Message(role="user", content="hello")]))

    assert [event.type for event in events] == [
        "run.started",
        "stage.started",
        "model.request.started",
        "response.delta",
        "model.response.completed",
        "run.completed",
    ]
    assert events[3].text == "first"


def test_report_mode_publishes_only_after_structured_evidence_validation() -> None:
    tool_call = {
        "index": 0,
        "id": "call-report",
        "type": "function",
        "function": {"name": "data:fetch_stock_data", "arguments": "{}"},
    }
    report = (
        '{"executive_summary":"Verified.","key_drivers":["Demand."],'
        '"detailed_analysis":"Close [[fact:prices:data.latest.close]].",'
        '"risks":["Execution."],"final_view":"Review.","claims":['
        '{"claim_id":"c1","text":"Close [[fact:prices:data.latest.close]].",'
        '"importance":"major","evidence_refs":["src"],'
        '"numeric_refs":["prices:data.latest.close"]}],'
        '"citations":[{"citation_id":"src","source_id":"prices"}]}'
    )
    model = FakeModel(
        [
            [
                {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": [tool_call]}}]},
                }
            ],
            [{"event": "token", "data": report}],
        ]
    )
    persisted: list[Message] = []
    loop = AgentLoop(
        model,
        ReportTools(),
        config=AgentLoopConfig(mode="autonomous", publish_reports=True),
    )

    events = asyncio.run(
        _collect(
            loop,
            [Message(role="user", content="publish a report")],
            message_writer=persisted.append,
        )
    )

    deltas = "".join(event.text for event in events if event.type == "response.delta")
    assert "123.4 provider_value" in deltas
    assert persisted[-1].content == deltas
    assert (
        next(event for event in events if event.type == "run.completed").terminal_status
        == "success"
    )


def test_report_mode_holds_invalid_draft_without_leaking_text() -> None:
    model = FakeModel([[{"event": "token", "data": "{not-json-secret-123}"}]])
    persisted: list[Message] = []
    loop = AgentLoop(
        model,
        ReportTools(),
        config=AgentLoopConfig(mode="autonomous", publish_reports=True),
    )

    events = asyncio.run(
        _collect(
            loop,
            [Message(role="user", content="publish a report")],
            message_writer=persisted.append,
        )
    )

    output = "".join(event.text for event in events if event.type == "response.delta")
    assert "secret-123" not in output
    assert "secret-123" not in "".join(message.content for message in persisted)
    assert (
        next(event for event in events if event.type == "run.completed").terminal_status
        == "needs_review"
    )


def test_loop_renders_content_from_openai_chunk_frames() -> None:
    model = FakeModel(
        [
            [
                {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"content": "chunked answer"}}]},
                }
            ]
        ]
    )
    loop = AgentLoop(model, FakeTools())

    events = asyncio.run(_collect(loop, [Message(role="user", content="hello")]))

    deltas = [event.text for event in events if event.type == "response.delta"]
    assert "".join(deltas) == "chunked answer"
    assert events[-1].type == "run.completed"


def test_loop_exposes_provider_attempt_events_to_the_ui() -> None:
    model = FakeModel(
        [
            [
                {"event": "provider_attempt_started", "data": {"attempt": 1}},
                {
                    "event": "provider_stream_started",
                    "data": {"attempt": 1, "first_byte_ms": 12},
                },
                {"event": "token", "data": "first"},
                {
                    "event": "provider_completed",
                    "data": {"attempts": 1, "duration_ms": 25},
                },
            ]
        ]
    )
    loop = AgentLoop(model, FakeTools())

    events = asyncio.run(_collect(loop, [Message(role="user", content="hello")]))

    assert [event.type for event in events if event.type.startswith("provider.")] == [
        "provider.attempt.started",
        "provider.stream.started",
        "provider.completed",
    ]


def test_loop_preserves_substantive_output_when_provider_stream_disconnects() -> None:
    loop = AgentLoop(InterruptedModel(), FakeTools())

    events = asyncio.run(_collect(loop, [Message(role="user", content="hello")]))

    assert any(event.type == "provider.failed" for event in events)
    assert not any(event.type == "run.failed" for event in events)
    assert events[-1].type == "run.completed"
    assert events[-1].terminal_status == "partial"


def test_loop_records_tool_call_and_returns_to_model() -> None:
    tool_call = {
        "index": 0,
        "id": "call-1",
        "type": "function",
        "function": {"name": "data:lookup", "arguments": '{"ticker":"HDFCBANK"}'},
    }
    model = FakeModel(
        [
            [
                {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": [tool_call]}}]},
                }
            ],
            [{"event": "token", "data": "evidence"}],
        ]
    )
    loop = AgentLoop(model, FakeTools(), config=AgentLoopConfig(mode="autonomous"))

    events = asyncio.run(_collect(loop, [Message(role="user", content="find HDFC")]))

    assert any(event.type == "tool.started" for event in events)
    assert any(event.type == "tool.completed" for event in events)
    assert events[-1].type == "run.completed"
    assert model.calls[1][-1].role == "tool"
    assert json.loads(model.calls[1][-1].content)["data"]["ticker"] == "HDFCBANK"


def test_loop_marks_run_partial_when_evidence_tool_fails() -> None:
    tool_call = {
        "index": 0,
        "id": "call-failed",
        "type": "function",
        "function": {"name": "analysis:run_technical_scan", "arguments": "{}"},
    }
    model = FakeModel(
        [
            [
                {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": [tool_call]}}]},
                }
            ],
        ]
    )
    loop = AgentLoop(model, FailedTools(), config=AgentLoopConfig(mode="autonomous"))

    events = asyncio.run(_collect(loop, [Message(role="user", content="analyse HDFC")]))

    completed = next(event for event in events if event.type == "run.completed")
    assert completed.terminal_status == "insufficient_data"
    assert any(event.type == "tool.failed" for event in events)
    assert "no usable data" in "".join(
        event.text for event in events if event.type == "response.delta"
    )
    assert len(model.calls) == 1


def test_loop_recovers_from_malformed_tool_arguments() -> None:
    malformed_call = {
        "index": 0,
        "id": "call-bad",
        "type": "function",
        "function": {
            "name": "data:lookup",
            "arguments": '{"ticker":"HDFCBANK"',
        },
    }
    model = FakeModel(
        [
            [
                {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": [malformed_call]}}]},
                }
            ],
            [{"event": "token", "data": "recovered"}],
        ]
    )
    loop = AgentLoop(model, FakeTools(), config=AgentLoopConfig(mode="autonomous"))

    events = asyncio.run(_collect(loop, [Message(role="user", content="find HDFC")]))

    assert any(event.type == "tool.failed" for event in events)
    assert events[-3].type == "response.delta"
    assert events[-3].text == "recovered"
    assert events[-1].type == "run.completed"
    assert model.calls[1][-1].role == "tool"
    assert "ticker" in model.calls[1][-1].content


def test_loop_pauses_on_malformed_clarification_call() -> None:
    malformed_call = {
        "index": 0,
        "id": "call-clarify",
        "type": "function",
        "function": {
            "name": "interaction:ask_user",
            "arguments": '{"question":"Which timeframe',
        },
    }
    model = FakeModel(
        [
            [
                {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": [malformed_call]}}]},
                }
            ]
        ]
    )
    loop = AgentLoop(model, FakeTools())

    events = asyncio.run(_collect(loop, [Message(role="user", content="analyse HDFC")]))

    assert events[-1].type == "clarification.requested"
    assert not any(event.type == "run.failed" for event in events)


def test_loop_injects_selected_skill_without_persisting_it_as_user_context() -> None:
    model = FakeModel([[{"event": "token", "data": "grounded answer"}]])
    loop = AgentLoop(model, FakeTools(), skill_registry=SkillRegistry.bundled())

    events = asyncio.run(
        _collect(loop, [Message(role="user", content="Compare revenue and margins")])
    )

    assert any(event.type == "skill.selected" for event in events)
    assert model.calls[0][0].role == "system"
    assert "fundamental-analysis" in model.calls[0][0].content


def test_guided_loop_pauses_before_external_tool_and_writes_checkpoint() -> None:
    tool_call = {
        "index": 0,
        "id": "call-approval",
        "type": "function",
        "function": {"name": "data:lookup", "arguments": '{"ticker":"AAPL"}'},
    }
    model = FakeModel(
        [
            [
                {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": [tool_call]}}]},
                }
            ]
        ]
    )
    checkpoints: list[dict] = []
    loop = AgentLoop(model, FakeTools())

    events = asyncio.run(
        _collect(
            loop,
            [Message(role="user", content="research Apple")],
            checkpoint_writer=checkpoints.append,
        )
    )

    assert events[-1].type == "approval.requested"
    assert checkpoints[0]["tool_call_id"] == "call-approval"
    assert checkpoints[0]["status"] == "awaiting_approval"


def test_guided_loop_executes_approved_checkpoint_before_calling_model() -> None:
    approved_call = {
        "id": "call-approved",
        "type": "function",
        "function": {"name": "data:lookup", "arguments": '{"ticker":"HDFCBANK.NS"}'},
    }
    next_call = {
        "id": "call-next",
        "type": "function",
        "function": {"name": "data:lookup", "arguments": '{"ticker":"INFY.NS"}'},
    }
    history = [
        Message(role="user", content="compare HDFC Bank and Infosys"),
        Message(role="assistant", content="", tool_calls=[approved_call, next_call]),
    ]
    model = FakeModel([])
    checkpoints: list[dict] = []
    loop = AgentLoop(model, FakeTools())

    events = asyncio.run(
        _collect(
            loop,
            history,
            approved_tool_ids={"call-approved"},
            checkpoint_writer=checkpoints.append,
        )
    )

    assert not model.calls
    assert any(
        event.type == "tool.completed" and event.tool_id == "call-approved"
        for event in events
    )
    assert events[-1].type == "approval.requested"
    assert checkpoints[-1]["tool_call_id"] == "call-next"


def test_guided_loop_does_not_repeat_completed_checkpoint_tools() -> None:
    first_call = {
        "id": "call-first",
        "type": "function",
        "function": {"name": "data:lookup", "arguments": '{"ticker":"HDFCBANK.NS"}'},
    }
    approved_call = {
        "id": "call-approved",
        "type": "function",
        "function": {"name": "data:lookup", "arguments": '{"ticker":"INFY.NS"}'},
    }
    next_call = {
        "id": "call-next",
        "type": "function",
        "function": {"name": "data:lookup", "arguments": '{"ticker":"TCS.NS"}'},
    }
    history = [
        Message(role="user", content="compare three banks"),
        Message(
            role="assistant",
            content="",
            tool_calls=[first_call, approved_call, next_call],
        ),
        Message(
            role="tool",
            content='{"success":true}',
            tool_call_id="call-first",
        ),
    ]
    model = FakeModel([])
    checkpoints: list[dict] = []
    tools = FakeTools()
    loop = AgentLoop(model, tools)

    events = asyncio.run(
        _collect(
            loop,
            history,
            approved_tool_ids={"call-approved"},
            checkpoint_writer=checkpoints.append,
        )
    )

    completed_ids = [
        event.tool_id for event in events if event.type == "tool.completed"
    ]
    assert completed_ids == ["call-approved"]
    assert events[-1].type == "approval.requested"
    assert checkpoints[-1]["tool_call_id"] == "call-next"


def test_broad_finance_request_keeps_model_tool_catalog_bounded() -> None:
    model = FakeModel([[{"event": "token", "data": "answer"}]])
    loop = AgentLoop(model, FakeTools(), skill_registry=SkillRegistry.bundled())

    asyncio.run(_collect(loop, [Message(role="user", content="Analyse HDFC stock")]))

    assert len(model.calls) == 1
    assert len(model.request_kwargs[0]["tools"]) <= 8
    assert model.request_kwargs[0]["max_tokens"] == 512
    assert model.request_kwargs[0]["temperature"] == 0.1


def test_research_response_without_evidence_is_not_marked_success() -> None:
    model = FakeModel([[{"event": "token", "data": "unsupported summary"}]])
    loop = AgentLoop(model, FakeTools(), skill_registry=SkillRegistry.bundled())

    events = asyncio.run(
        _collect(loop, [Message(role="user", content="Analyse HDFC stock")])
    )

    assert events[-1].type == "run.completed"
    assert events[-1].terminal_status == "insufficient_data"


async def _collect(loop: AgentLoop, messages: list[Message], **kwargs):
    return [
        event async for event in loop.run(messages, conversation_id=uuid4(), **kwargs)
    ]
