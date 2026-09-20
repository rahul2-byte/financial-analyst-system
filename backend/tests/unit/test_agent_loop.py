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


class EmptyFailureModel:
    def generate_stream(self, messages: list[Message], model: str, **kwargs):
        del messages, model, kwargs

        async def stream():
            raise TimeoutError("provider stalled before content")
            yield  # pragma: no cover

        return stream()


class HiddenReasoningTimeoutModel:
    def __init__(self, tool_call: dict) -> None:
        self.tool_call = tool_call
        self.calls = 0

    def generate_stream(self, messages: list[Message], model: str, **kwargs):
        del messages, model, kwargs
        self.calls += 1

        async def stream():
            if self.calls == 1:
                yield {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": [self.tool_call]}}]},
                }
                return
            yield {
                "event": "provider_stream_started",
                "data": {"attempt": 1, "first_byte_ms": 10.0},
            }
            yield {
                "event": "chunk",
                "data": {
                    "choices": [{"delta": {"reasoning_content": "hidden reasoning"}}]
                },
            }
            raise TimeoutError("provider stalled")

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
                "source_url": "https://fixture.example",
            },
        }


class ValidationRepairTimeoutModel:
    def __init__(self, tool_call: dict, invalid_report: str) -> None:
        self.tool_call = tool_call
        self.invalid_report = invalid_report
        self.calls = 0

    def generate_stream(self, messages, model, **kwargs):
        del messages, model, kwargs
        self.calls += 1

        async def stream():
            if self.calls == 1:
                yield {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": [self.tool_call]}}]},
                }
            elif self.calls == 2:
                yield {"event": "token", "data": self.invalid_report}
            else:
                yield {"event": "token", "data": self.invalid_report}
                raise TimeoutError("repair provider stalled")

        return stream()


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


def test_empty_visible_model_response_retries_with_full_budget() -> None:
    model = FakeModel(
        [
            [{"event": "provider_completed", "data": {"attempts": 1}}],
            [{"event": "token", "data": "recovered"}],
        ]
    )
    loop = AgentLoop(model, FakeTools(), config=AgentLoopConfig(max_tokens=8192))

    events = asyncio.run(_collect(loop, [Message(role="user", content="hello")]))

    assert any(
        event.type == "response.delta" and event.text == "recovered" for event in events
    )
    assert model.request_kwargs[0]["max_tokens"] == 1024
    assert model.request_kwargs[1]["max_tokens"] == 8192


def test_report_mode_publishes_only_after_structured_evidence_validation() -> None:
    tool_call = {
        "index": 0,
        "id": "call-report",
        "type": "function",
        "function": {"name": "data:fetch_stock_data", "arguments": '{"ticker":"ABC"}'},
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
    assert "123.4" in deltas
    assert persisted[-1].content == deltas
    assert "executive_summary" in model.calls[0][-1].content
    assert "numeric_refs" in model.calls[0][-1].content
    assert model.request_kwargs[1]["max_tokens"] == 32768
    assert (
        next(event for event in events if event.type == "run.completed").terminal_status
        == "completed"
    )


def test_hidden_reasoning_timeout_returns_partial_evidence_fallback() -> None:
    tool_call = {
        "index": 0,
        "id": "call-report-timeout",
        "type": "function",
        "function": {"name": "data:fetch_stock_data", "arguments": '{"ticker":"ABC"}'},
    }
    model = HiddenReasoningTimeoutModel(tool_call)
    loop = AgentLoop(
        model,
        ReportTools(),
        config=AgentLoopConfig(mode="autonomous", publish_reports=True),
    )

    events = asyncio.run(
        _collect(loop, [Message(role="user", content="publish a report")])
    )

    assert events[-1].type == "run.failed"
    assert events[-1].category == "model_generation"
    response = "".join(event.text for event in events if event.type == "response.delta")
    assert response == ""
    assert "hidden reasoning" not in response


def test_source_events_include_the_verified_provider_url() -> None:
    tool_call = {
        "index": 0,
        "id": "call-source",
        "type": "function",
        "function": {"name": "data:fetch_stock_data", "arguments": '{"ticker":"ABC"}'},
    }
    model = FakeModel(
        [
            [
                {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": [tool_call]}}]},
                }
            ],
            [{"event": "token", "data": "done"}],
        ]
    )
    events = asyncio.run(
        _collect(AgentLoop(model, ReportTools()), [Message(role="user", content="ABC")])
    )

    source_event = next(event for event in events if event.type == "sources.updated")
    assert source_event.sources == [
        {"name": "fixture", "url": "https://fixture.example"}
    ]


def test_report_mode_returns_useful_failure_response_without_leaking_draft() -> None:
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
    assert output == ""
    assert "secret-123" not in "".join(message.content for message in persisted)
    assert events[-1].type == "run.failed"


def test_invalid_report_returns_verification_summary_with_source() -> None:
    tool_call = {
        "index": 0,
        "id": "call-report",
        "type": "function",
        "function": {"name": "data:fetch_stock_data", "arguments": '{"ticker":"ABC"}'},
    }
    model = FakeModel(
        [
            [
                {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": [tool_call]}}]},
                }
            ],
            [{"event": "token", "data": "A useful partial report. " * 12}],
            [{"event": "token", "data": "still not valid JSON"}],
        ]
    )
    loop = AgentLoop(model, ReportTools(), config=AgentLoopConfig(publish_reports=True))

    events = asyncio.run(_collect(loop, [Message(role="user", content="report")]))

    output = "".join(event.text for event in events if event.type == "response.delta")
    assert "Verified evidence" in output
    assert "No unsupported investment conclusion" in output
    assert events[-1].type == "run.completed"
    assert events[-1].terminal_status == "completed_with_limited_evidence"


def test_interrupted_report_stream_still_returns_a_response() -> None:
    loop = AgentLoop(
        InterruptedModel(), ReportTools(), config=AgentLoopConfig(publish_reports=True)
    )

    events = asyncio.run(_collect(loop, [Message(role="user", content="report")]))

    output = "".join(event.text for event in events if event.type == "response.delta")
    assert output == ""
    assert events[-1].type == "run.failed"


def test_empty_report_provider_failure_still_returns_explicit_report() -> None:
    loop = AgentLoop(
        EmptyFailureModel(), ReportTools(), config=AgentLoopConfig(publish_reports=True)
    )

    events = asyncio.run(_collect(loop, [Message(role="user", content="report")]))

    output = "".join(event.text for event in events if event.type == "response.delta")
    assert events[-1].type == "run.failed"
    assert output == ""


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
        "function": {
            "name": "analysis:run_technical_scan",
            "arguments": '{"ticker":"HDFCBANK.NS"}',
        },
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


def test_report_mode_renders_when_all_evidence_tools_fail() -> None:
    tool_call = {
        "index": 0,
        "id": "call-report-failed",
        "type": "function",
        "function": {
            "name": "analysis:run_technical_scan",
            "arguments": '{"ticker":"HDFCBANK.NS"}',
        },
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
    loop = AgentLoop(model, FailedTools(), config=AgentLoopConfig(publish_reports=True))

    events = asyncio.run(_collect(loop, [Message(role="user", content="report")]))

    output = "".join(event.text for event in events if event.type == "response.delta")
    assert events[-1].type == "run.failed"
    assert output == ""


def test_report_mode_parses_model_content_after_optional_tool_failure() -> None:
    tool_call = {
        "index": 0,
        "id": "call-news-failed",
        "type": "function",
        "function": {
            "name": "news:fetch_news",
            "arguments": '{"ticker":"ABC"}',
        },
    }
    report = (
        '{"executive_summary":"Verified.","key_drivers":["Demand."],'
        '"detailed_analysis":"No news conclusion is made.","risks":["Execution."],'
        '"final_view":"Review.","claims":[{"claim_id":"c1",'
        '"text":"Demand remains relevant.","importance":"major",'
        '"evidence_refs":["src"],"numeric_refs":[]}],'
        '"citations":[{"citation_id":"src","source_id":"fixture"}]}'
    )

    class NewsFailedTools(ReportTools):
        def definitions(self) -> list[dict]:
            return [
                {"type": "function", "function": {"name": "news:fetch_news"}},
                {"type": "function", "function": {"name": "data:fetch_stock_data"}},
            ]

        async def execute(self, name: str, arguments: dict) -> dict:
            if name == "news:fetch_news":
                return {"success": False, "error": "news timeout"}
            return await super().execute(name, arguments)

    price_call = {
        **tool_call,
        "index": 1,
        "id": "call-price",
        "function": {
            "name": "data:fetch_stock_data",
            "arguments": '{"ticker":"ABC"}',
        },
    }
    model = FakeModel(
        [
            [
                {
                    "event": "chunk",
                    "data": {
                        "choices": [{"delta": {"tool_calls": [tool_call, price_call]}}]
                    },
                }
            ],
            [{"event": "token", "data": report}],
        ]
    )

    events = asyncio.run(
        _collect(
            AgentLoop(
                model, NewsFailedTools(), config=AgentLoopConfig(publish_reports=True)
            ),
            [Message(role="user", content="report")],
        )
    )

    assert events[-1].type == "run.completed"
    assert events[-1].terminal_status == "completed_with_limited_evidence"
    output = "".join(event.text for event in events if event.type == "response.delta")
    assert "Demand remains relevant." in output
    assert "news" in output.lower()


def test_report_mode_converts_runtime_failure_to_explicit_report() -> None:
    loop = AgentLoop(
        FakeModel([]),
        FakeTools(),
        config=AgentLoopConfig(publish_reports=True, max_rounds=0),
    )

    events = asyncio.run(_collect(loop, [Message(role="user", content="report")]))

    output = "".join(event.text for event in events if event.type == "response.delta")
    assert events[-1].type == "run.failed"
    assert output == ""


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


def test_recoverable_financial_tool_arguments_do_not_degrade_a_recovered_run() -> None:
    invalid_call = {
        "index": 0,
        "id": "call-invalid",
        "type": "function",
        "function": {"name": "analysis:run_fundamental_scan", "arguments": "{}"},
    }
    valid_call = {
        "index": 0,
        "id": "call-valid",
        "type": "function",
        "function": {
            "name": "analysis:run_fundamental_scan",
            "arguments": '{"ticker":"HDFCBANK.NS"}',
        },
    }

    class FundamentalTools:
        def definitions(self):
            return [
                {
                    "type": "function",
                    "function": {"name": "analysis:run_fundamental_scan"},
                }
            ]

        async def execute(self, name, arguments):
            assert name == "analysis:run_fundamental_scan"
            return {"success": True, "data": {"ticker": arguments["ticker"]}}

    model = FakeModel(
        [
            [
                {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": [invalid_call]}}]},
                }
            ],
            [
                {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": [valid_call]}}]},
                }
            ],
            [{"event": "token", "data": "verified"}],
        ]
    )
    events = asyncio.run(
        _collect(
            AgentLoop(model, FundamentalTools()),
            [Message(role="user", content="analyse HDFC Bank")],
        )
    )

    assert any(event.type == "tool.failed" for event in events)
    assert any(event.type == "tool.completed" for event in events)
    assert events[-1].terminal_status == "success"


def test_report_mode_repairs_a_plain_text_draft_once() -> None:
    tool_call = {
        "index": 0,
        "id": "call-report-repair",
        "type": "function",
        "function": {"name": "data:fetch_stock_data", "arguments": '{"ticker":"ABC"}'},
    }
    repaired_report = (
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
            [{"event": "token", "data": "The stock looks strong."}],
            [{"event": "token", "data": repaired_report}],
        ]
    )
    events = asyncio.run(
        _collect(
            AgentLoop(
                model, ReportTools(), config=AgentLoopConfig(publish_reports=True)
            ),
            [Message(role="user", content="report on ABC")],
        )
    )

    assert len(model.calls) == 3
    assert "formatting repair" in model.calls[-1][-1].content.lower()
    assert model.request_kwargs[-1]["tools"] == []
    assert "123.4" in "".join(
        event.text for event in events if event.type == "response.delta"
    )
    assert events[-1].terminal_status == "completed"


def test_report_mode_repairs_publication_validation_once() -> None:
    tool_call = {
        "index": 0,
        "id": "call-report-validation-repair",
        "type": "function",
        "function": {"name": "data:fetch_stock_data", "arguments": '{"ticker":"ABC"}'},
    }
    base = (
        '{"executive_summary":"Verified.","key_drivers":["Demand."],'
        '"detailed_analysis":"Close [[fact:prices:data.latest.close]].",'
        '"risks":["Execution."],"final_view":"Review.","claims":['
        '{"claim_id":"c1","text":"Close [[fact:prices:data.latest.close]].",'
        '"importance":"major","evidence_refs":["src"],'
        '"numeric_refs":["prices:data.latest.close"]}],'
    )
    invalid = base + '"citations":[{"citation_id":"src","source_id":"missing"}]}'
    valid = base + '"citations":[{"citation_id":"src","source_id":"prices"}]}'
    model = FakeModel(
        [
            [
                {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": [tool_call]}}]},
                }
            ],
            [{"event": "token", "data": invalid}],
            [{"event": "token", "data": valid}],
        ]
    )

    events = asyncio.run(
        _collect(
            AgentLoop(
                model, ReportTools(), config=AgentLoopConfig(publish_reports=True)
            ),
            [Message(role="user", content="report on ABC")],
        )
    )

    assert events[-1].type == "run.completed"
    assert events[-1].terminal_status == "completed"
    assert "citation_source_missing" in model.calls[-1][-1].content


def test_report_repair_timeout_returns_verified_evidence_fallback() -> None:
    tool_call = {
        "index": 0,
        "id": "call-report-fallback",
        "type": "function",
        "function": {"name": "data:fetch_stock_data", "arguments": '{"ticker":"ABC"}'},
    }
    invalid_report = (
        '{"executive_summary":"Unsupported.","key_drivers":["Demand."],'
        '"detailed_analysis":"No validated claim.","risks":["Execution."],'
        '"final_view":"Review.","claims":[{"claim_id":"c1",'
        '"text":"Unsupported.","importance":"major",'
        '"evidence_refs":[],"numeric_refs":[]}]}'
    )
    model = ValidationRepairTimeoutModel(tool_call, invalid_report)
    events = asyncio.run(
        _collect(
            AgentLoop(
                model, ReportTools(), config=AgentLoopConfig(publish_reports=True)
            ),
            [Message(role="user", content="report on ABC")],
        )
    )

    output = "".join(event.text for event in events if event.type == "response.delta")
    assert events[-1].type == "run.completed"
    assert events[-1].terminal_status == "completed_with_limited_evidence"
    assert "Verified evidence" in output
    assert "No unsupported investment conclusion" in output


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


def test_guided_loop_runs_read_only_research_tool_without_approval() -> None:
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
            ],
            [{"event": "token", "data": "Research complete."}],
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

    assert any(event.type == "tool.completed" for event in events)
    assert events[-1].type == "run.completed"
    assert not any(event.type == "approval.requested" for event in events)
    assert checkpoints == []


def test_resumed_loop_executes_all_pending_read_only_tools() -> None:
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
    model = FakeModel([[{"event": "token", "data": "Both companies were checked."}]])
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

    assert len(model.calls) == 1
    assert any(
        event.type == "tool.completed" and event.tool_id == "call-approved"
        for event in events
    )
    assert any(
        event.type == "tool.completed" and event.tool_id == "call-next"
        for event in events
    )
    assert events[-1].type == "run.completed"
    assert checkpoints == []


def test_resumed_loop_does_not_repeat_completed_tools() -> None:
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
    model = FakeModel([[{"event": "token", "data": "Comparison complete."}]])
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
    assert completed_ids == ["call-approved", "call-next"]
    assert events[-1].type == "run.completed"
    assert checkpoints == []


def test_broad_finance_request_keeps_model_tool_catalog_bounded() -> None:
    model = FakeModel([[{"event": "token", "data": "answer"}]])
    loop = AgentLoop(model, FakeTools(), skill_registry=SkillRegistry.bundled())

    asyncio.run(_collect(loop, [Message(role="user", content="Analyse HDFC stock")]))

    assert len(model.calls) == 1
    assert len(model.request_kwargs[0]["tools"]) <= 8
    assert model.request_kwargs[0]["max_tokens"] == 1024
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
