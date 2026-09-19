from uuid import uuid4

import pytest
from app.core.agent_loop.evidence import EvidenceAccounting, extract_evidence_facts
from app.core.agent_loop.model_streaming import ModelStreaming
from app.core.agent_loop.runtime import _tool_message_content
from app.core.agent_loop.terminal_state import terminal_status
from app.core.agent_loop.tool_execution import ToolExecutor
from app.events.models import EventFactory
from app.models.request_models import Message


@pytest.mark.asyncio
async def test_tool_executor_converts_tool_exceptions_to_a_failure_payload() -> None:
    class BrokenTools:
        async def execute(self, name, arguments):
            del name, arguments
            raise RuntimeError("provider unavailable")

    payload = await ToolExecutor(BrokenTools()).execute("data:fetch_stock_data", {})

    assert payload["success"] is False
    assert "ticker" in payload["error"]
    assert payload["retryable"] is True


def test_evidence_accounting_rejects_invalid_provenance() -> None:
    accounting = EvidenceAccounting()
    accounting.record_success(
        "data:fetch_stock_data",
        {"data": {"latest": {"close": 1.0}}, "provenance": {}},
    )

    assert accounting.invalid_evidence is True


def test_evidence_fact_ids_normalize_provider_field_names() -> None:
    facts = extract_evidence_facts(
        {
            "data": {"first": {"Adj Close": 123.4}},
            "provenance": {
                "source": "fixture",
                "dataset": "historical_prices",
                "instrument": "ABC.NS",
                "observed_at": "2026-09-18T00:00:00+00:00",
                "ingested_at": "2026-09-18T00:01:00+00:00",
                "version": "fixture-1",
                "quality_status": "verified",
            },
        }
    )
    assert "historical_prices:data.first.Adj_Close" in facts


def test_tool_message_content_bounds_large_provider_results() -> None:
    value = _tool_message_content({"success": True, "data": "x" * 20_000})
    assert len(value) < 8_000
    assert '"truncated": true' in value


def test_terminal_state_marks_partial_provider_text_as_partial() -> None:
    assert (
        terminal_status(
            failed_tools=0,
            successful_tools=0,
            requires_evidence=False,
            successful_evidence_tools=0,
            invalid_evidence=False,
            partial_provider_response=True,
        )
        == "partial"
    )


@pytest.mark.asyncio
async def test_model_streaming_converts_provider_tokens_to_assistant_message() -> None:
    class Model:
        def generate_stream(self, messages, model, **kwargs):
            del messages, model, kwargs

            async def stream():
                yield {"event": "token", "data": "answer"}

            return stream()

    stream = ModelStreaming(Model(), "fixture", 128, list)
    events = [item async for item in stream.stream([], EventFactory(uuid4()), 1)]

    assert events[-1].content == "answer"


@pytest.mark.asyncio
async def test_report_model_gets_room_after_tool_evidence() -> None:
    requests = []

    class Model:
        def generate_stream(self, messages, model, **kwargs):
            del messages, model
            requests.append(kwargs)

            async def stream():
                yield {"event": "token", "data": "answer"}

            return stream()

    stream = ModelStreaming(
        Model(), "fixture", 4096, list, publish_reports=True, report_max_tokens=8192
    )
    events = [
        item
        async for item in stream.stream(
            [Message(role="tool", content="{}", tool_call_id="call")],
            EventFactory(uuid4()),
            1,
        )
    ]

    assert events[-1].content == "answer"
    assert requests[0]["max_tokens"] == 8192
