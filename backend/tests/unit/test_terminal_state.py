from uuid import uuid4

from app.events.models import (
    EventFactory,
    RunCompleted,
    RunStarted,
    StageStarted,
    TextDelta,
    ToolCompleted,
    ToolFailed,
    ToolStarted,
)
from finai.state import PresentationPhase, PresentationState, reduce_event


def test_reducer_tracks_public_response_and_terminal_status() -> None:
    factory = EventFactory(conversation_id=uuid4())
    state = PresentationState()

    for event in (
        factory.make(RunStarted, query="Analyze INFY"),
        factory.make(StageStarted, stage="research", label="Research"),
        factory.make(TextDelta, text="Revenue increased."),
        factory.make(RunCompleted, terminal_status="success", duration_ms=123.0),
    ):
        state = reduce_event(state, event)

    assert state.phase is PresentationPhase.COMPLETE
    assert state.response_text == "Revenue increased."
    assert state.terminal_status == "success"


def test_reducer_ignores_duplicate_sequence() -> None:
    factory = EventFactory(conversation_id=uuid4())
    state = reduce_event(PresentationState(), factory.make(RunStarted, query="INFY"))
    event = factory.make(TextDelta, text="once")
    state = reduce_event(state, event)
    duplicate = event.model_copy(
        update={"meta": event.meta.model_copy(update={"sequence": 2})}
    )

    state = reduce_event(state, duplicate)

    assert state.response_text == "once"


def test_reducer_tracks_current_operation_and_active_tools() -> None:
    factory = EventFactory(conversation_id=uuid4())
    state = PresentationState()
    for event in (
        factory.make(RunStarted, query="Analyze INFY"),
        factory.make(StageStarted, stage="research", label="Searching filings"),
        factory.make(ToolStarted, tool="SEC filings", detail="10-Q and annual reports"),
    ):
        state = reduce_event(state, event)

    assert state.current_operation == "SEC filings"
    assert state.active_tools == ("SEC filings",)

    state = reduce_event(
        state, factory.make(ToolCompleted, tool="SEC filings", detail="8 sources")
    )
    assert state.active_tools == ()


def test_reducer_keeps_concurrent_same_name_tools_separate() -> None:
    factory = EventFactory(conversation_id=uuid4())
    state = reduce_event(
        PresentationState(),
        factory.make(ToolStarted, tool="SEC filings", tool_id="tool-1"),
    )
    state = reduce_event(
        state,
        factory.make(ToolStarted, tool="SEC filings", tool_id="tool-2"),
    )

    assert state.active_tools == ("tool-1", "tool-2")
    assert set(state.activities) == {"tool:tool-1", "tool:tool-2"}

    state = reduce_event(
        state,
        factory.make(ToolCompleted, tool="SEC filings", tool_id="tool-1"),
    )
    assert state.active_tools == ("tool-2",)


def test_reducer_closes_operations_on_terminal_event() -> None:
    factory = EventFactory(conversation_id=uuid4())
    state = PresentationState()
    state = reduce_event(
        state, factory.make(StageStarted, stage="research", label="Searching")
    )
    state = reduce_event(state, factory.make(RunCompleted, terminal_status="success"))

    assert state.current_operation is None
    assert state.active_tools == ()


def test_reducer_keeps_unstarted_tool_failure_visible() -> None:
    factory = EventFactory(conversation_id=uuid4())
    state = reduce_event(
        PresentationState(),
        factory.make(
            ToolFailed,
            tool="analysis:run_technical_scan",
            tool_id="call-bad",
            message="invalid arguments",
        ),
    )

    assert state.activities["tool:call-bad"].status == "failed"
    assert state.activities["tool:call-bad"].detail == "invalid arguments"
