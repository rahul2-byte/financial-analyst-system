"""Presentation-level event classification for the Textual application."""

from __future__ import annotations

ACTIVITY_EVENTS = frozenset(
    {
        "skill.selected",
        "model.request.started",
        "provider.attempt.started",
        "provider.retrying",
        "provider.stream.started",
        "provider.completed",
        "provider.failed",
        "tool.progress",
        "context.compacted",
        "stage.started",
        "stage.completed",
        "stage.failed",
        "tool.started",
        "tool.completed",
        "tool.failed",
        "run.completed",
        "run.cancelled",
        "run.failed",
    }
)
TERMINAL_EVENTS = frozenset({"run.completed", "run.cancelled", "run.failed"})
TOOL_EVENTS = frozenset({"tool.started", "tool.progress"})


def is_activity_event(event_type: str) -> bool:
    return event_type in ACTIVITY_EVENTS


def is_terminal_event(event_type: str) -> bool:
    return event_type in TERMINAL_EVENTS


def is_tool_event(event_type: str) -> bool:
    return event_type in TOOL_EVENTS
