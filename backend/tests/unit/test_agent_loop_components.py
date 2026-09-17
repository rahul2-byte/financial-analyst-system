from uuid import uuid4

import pytest
from app.core.agent_loop.evidence import EvidenceAccounting
from app.core.agent_loop.model_streaming import ModelStreaming
from app.core.agent_loop.terminal_state import terminal_status
from app.core.agent_loop.tool_execution import ToolExecutor
from app.events.models import EventFactory


@pytest.mark.asyncio
async def test_tool_executor_converts_tool_exceptions_to_a_failure_payload() -> None:
    class BrokenTools:
        async def execute(self, name, arguments):
            del name, arguments
            raise RuntimeError("provider unavailable")

    payload = await ToolExecutor(BrokenTools()).execute("data:fetch_stock_data", {})

    assert payload == {"success": False, "error": "provider unavailable"}


def test_evidence_accounting_rejects_invalid_provenance() -> None:
    accounting = EvidenceAccounting()
    accounting.record_success(
        "data:fetch_stock_data",
        {"data": {"latest": {"close": 1.0}}, "provenance": {}},
    )

    assert accounting.invalid_evidence is True


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

    stream = ModelStreaming(Model(), "fixture", 128, False, list)
    events = [item async for item in stream.stream([], EventFactory(uuid4()), 1)]

    assert events[-1].content == "answer"
