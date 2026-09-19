from uuid import uuid4

from app.events.models import EventFactory, RunCompleted
from finai.plain import render_event


def test_completed_run_displays_saved_artifact_path() -> None:
    event = EventFactory(uuid4()).make(
        RunCompleted,
        terminal_status="partial",
        artifact_path=".finai/sessions/example/runs/run.json",
    )

    rendered = render_event(event)

    assert "Partial response" in rendered
    assert ".finai/sessions/example/runs/run.json" in rendered
