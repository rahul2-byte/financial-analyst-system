from pathlib import Path

from app.models.request_models import Message
from finai.app_commands import history_text, status_text, trace_text
from finai.state import PresentationPhase, PresentationState


def test_command_formatters_preserve_existing_status_and_history_text() -> None:
    state = PresentationState(phase=PresentationPhase.COMPLETE, latest_sequence=4)

    assert status_text(state) == "\nFIN-AI · complete · sequence 4"
    assert (
        history_text([Message(role="user", content="Analyze INFY")])
        == "\nuser: Analyze INFY"
    )


def test_trace_formatter_supports_human_and_json_views() -> None:
    records = [{"sequence": 1, "event_type": "run.started"}]

    assert "#1 run.started" in trace_text(records, Path("events.jsonl"))
    assert '"event_type": "run.started"' in trace_text(
        records, Path("events.jsonl"), as_json=True
    )
