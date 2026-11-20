"""Plain and JSON event renderers for pipes, CI, and debugging."""

from __future__ import annotations

import json
from collections.abc import Iterable
from urllib.parse import urlparse

from app.events.models import ResearchEvent

from .safety import sanitize_terminal_text


def render_sources_plain(sources: list[dict[str, str]]) -> str:
    lines = [f"\nSources · {len(sources)}"]
    for index, source in enumerate(sources, 1):
        url = source.get("url", "")
        title = source.get("title") or source.get("source") or "Untitled source"
        publisher = (
            source.get("publisher")
            or source.get("source")
            or urlparse(url).netloc
            or source.get("source_type", "")
        )
        lines.append(
            f"[{index}] {sanitize_terminal_text(title)}"
            + (f" — {sanitize_terminal_text(publisher)}" if publisher else "")
        )
        if url:
            lines.append(f"    {sanitize_terminal_text(url)}")
    return "\n".join(lines) + "\n"


def render_event(event: ResearchEvent, session_id: str | None = None) -> str:
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
        return render_sources_plain(event.sources)
    if event.type == "approval.requested":
        return f"\n? Approval required\n{sanitize_terminal_text(event.prompt)}\n"
    if event.type == "clarification.requested":
        session = (
            f'Session: {session_id}\nReply with: --session {session_id} "<your answer>"\n'
            if session_id
            else ""
        )
        return (
            "\nFIN-AI needs clarification\n"
            f"{sanitize_terminal_text(event.prompt)}\n{session}"
        )
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
            "completed_with_limited_evidence": "Completed with limited evidence",
        }.get(event.terminal_status, "Completed")
        artifact = (
            f"  Run artifact: {sanitize_terminal_text(event.artifact_path)}\n"
            if event.artifact_path
            else ""
        )
        return f"\n✓ {label}{duration}\n{artifact}"
    return ""


def render_plain(events: Iterable[ResearchEvent], session_id: str | None = None) -> str:
    return "".join(render_event(event, session_id) for event in events)


def render_json(events: Iterable[ResearchEvent]) -> str:
    return (
        json.dumps([event.model_dump(mode="json") for event in events], indent=2) + "\n"
    )
