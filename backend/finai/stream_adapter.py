"""Bridge the existing legacy orchestrator stream to typed terminal events."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from app.events.models import (
    ApprovalRequested,
    ClarificationRequested,
    EventFactory,
    ResearchEvent,
    RunCompleted,
    RunFailed,
    RunStarted,
    SourcesUpdated,
    StageStarted,
    TextDelta,
    ToolCompleted,
    ToolFailed,
    ToolStarted,
)
from app.models.response_models import StreamEvent

_MAX_PRESENTATION_DELTA = 64


def _status_label(message: str) -> str:
    raw = message.removeprefix("Pipeline processing: ").removesuffix("...").strip()
    if raw.startswith("_route"):
        return ""
    return message.removesuffix("...").strip()


async def adapt_legacy_stream(
    events: AsyncIterator[StreamEvent], *, conversation_id: UUID, query: str
) -> AsyncIterator[ResearchEvent]:
    """Map current SSE-shaped events without exposing raw provider payloads."""
    factory = EventFactory(conversation_id)
    yield factory.make(RunStarted, query=query)
    waiting_for_input = False
    status_number = 0
    last_status_label = ""
    seen_status_labels: set[str] = set()
    terminal_status = "success"
    async for event in events:
        if event.type == "status" and event.message:
            label = _status_label(event.message)
            if not label or label == last_status_label or label in seen_status_labels:
                continue
            last_status_label = label
            seen_status_labels.add(label)
            status_number += 1
            yield factory.make(StageStarted, stage=f"research-{status_number}", label=label)
        elif event.type == "text_delta" and event.content:
            for offset in range(0, len(event.content), _MAX_PRESENTATION_DELTA):
                yield factory.make(
                    TextDelta,
                    text=event.content[offset : offset + _MAX_PRESENTATION_DELTA],
                )
        elif event.type == "tool_status" and event.tool_name:
            if event.status in {"completed", "success"}:
                yield factory.make(
                    ToolCompleted,
                    tool=event.tool_name,
                    tool_id=event.tool_id,
                    detail=event.output,
                )
            elif event.status in {"error", "failed"}:
                yield factory.make(
                    ToolFailed,
                    tool=event.tool_name,
                    tool_id=event.tool_id,
                    message=event.message or "tool failed",
                )
            else:
                yield factory.make(
                    ToolStarted,
                    tool=event.tool_name,
                    tool_id=event.tool_id,
                    detail=event.input,
                )
        elif event.type in {"approval_required", "manual_review_required"}:
            waiting_for_input = True
            yield factory.make(
                ApprovalRequested,
                prompt=event.message or "Review the proposed research step.",
            )
        elif event.type == "clarification_required":
            waiting_for_input = True
            yield factory.make(ClarificationRequested, prompt=event.message or "Please clarify the request.")
        elif event.type == "final_payload" and isinstance(event.payload, dict):
            payload_status = event.payload.get("status")
            if isinstance(payload_status, str) and payload_status in {
                "insufficient_data",
                "low_confidence",
                "failure",
                "failed",
                "partial",
            }:
                terminal_status = payload_status
            sources = event.payload.get("sources")
            if isinstance(sources, list) and all(isinstance(source, dict) for source in sources):
                normalized = [{str(key): str(value) for key, value in source.items()} for source in sources]
                yield factory.make(SourcesUpdated, sources=normalized)
        elif event.type == "error":
            yield factory.make(RunFailed, message=event.message or "pipeline failed")
        elif event.type == "done" and not waiting_for_input:
            yield factory.make(RunCompleted, terminal_status=terminal_status)
