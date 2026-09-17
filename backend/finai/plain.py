"""Plain and JSON event renderers for pipes, CI, and debugging."""

from __future__ import annotations

import json
from collections.abc import Iterable

from app.events.models import ResearchEvent

from .safety import sanitize_terminal_text


def render_event(event: ResearchEvent) -> str:
    if event.type == "run.started":
        return f"\nYou\n{sanitize_terminal_text(event.query)}\n\nFIN-AI\n"
    if event.type == "stage.started":
        return f"\n◉ {sanitize_terminal_text(event.label)}\n"
    if event.type == "tool.started":
        detail = f" · {sanitize_terminal_text(event.detail)}" if event.detail else ""
        return f"  ◉ {sanitize_terminal_text(event.tool)}{detail}\n"
    if event.type == "tool.completed":
        return f"  ✓ {sanitize_terminal_text(event.tool)}\n"
    if event.type == "tool.failed":
        return f"  ✗ {sanitize_terminal_text(event.tool)}: {sanitize_terminal_text(event.message)}\n"
    if event.type == "response.delta":
        return sanitize_terminal_text(event.text)
    if event.type == "sources.updated":
        return f"\nSources · {len(event.sources)}\n"
    if event.type == "approval.requested":
        return f"\n? Approval required\n{sanitize_terminal_text(event.prompt)}\n"
    if event.type == "clarification.requested":
        return f"\nFIN-AI needs clarification\n{sanitize_terminal_text(event.prompt)}\n"
    if event.type == "run.failed":
        return f"\n✗ {sanitize_terminal_text(event.category)}: {sanitize_terminal_text(event.message)}\n"
    if event.type == "run.cancelled":
        return "\n✓ Cancelled\n"
    if event.type == "run.completed":
        duration = (
            f" · {event.duration_ms:.0f}ms" if event.duration_ms is not None else ""
        )
        label = {
            "partial": "Partial response",
            "insufficient_data": "Insufficient evidence",
            "needs_review": "Held for review",
        }.get(event.terminal_status, "Completed")
        return f"\n✓ {label}{duration}\n"
    return ""


def render_plain(events: Iterable[ResearchEvent]) -> str:
    return "".join(render_event(event) for event in events)


def render_json(events: Iterable[ResearchEvent]) -> str:
    return (
        json.dumps([event.model_dump(mode="json") for event in events], indent=2) + "\n"
    )
