"""Pure presentation state and event reducer for the terminal client."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from uuid import UUID

from app.events.models import (
    ApprovalRequested,
    ApprovalResolved,
    ClarificationRequested,
    ModelRequestStarted,
    ProviderAttemptStarted,
    ProviderCompleted,
    ProviderFailed,
    ProviderRetrying,
    ProviderStreamStarted,
    ResearchEvent,
    RunCancelled,
    RunCompleted,
    RunFailed,
    RunStarted,
    SourcesUpdated,
    StageCompleted,
    StageFailed,
    StageStarted,
    TextDelta,
    ToolCompleted,
    ToolFailed,
    ToolProgress,
    ToolStarted,
)


class PresentationPhase(StrEnum):
    IDLE = "idle"
    STARTING = "starting"
    PLANNING = "planning"
    RESEARCHING = "researching"
    ANALYSING = "analysing"
    VALIDATING = "validating"
    GENERATING = "generating"
    CANCELLING = "cancelling"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    WAITING_FOR_CLARIFICATION = "waiting_for_clarification"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ActivityState:
    label: str
    status: str = "running"
    detail: str | None = None


@dataclass
class PresentationState:
    phase: PresentationPhase = PresentationPhase.IDLE
    run_id: UUID | None = None
    query: str | None = None
    response_text: str = ""
    response_delta_count: int = 0
    terminal_status: str | None = None
    error: str | None = None
    latest_sequence: int = 0
    last_event_type: str | None = None
    current_operation: str | None = None
    active_tools: tuple[str, ...] = ()
    activities: dict[str, ActivityState] = field(default_factory=dict)
    sources: list[dict[str, str]] = field(default_factory=list)


def _phase_for_stage(stage: str) -> PresentationPhase:
    return {
        "planning": PresentationPhase.PLANNING,
        "research": PresentationPhase.RESEARCHING,
        "analysis": PresentationPhase.ANALYSING,
        "validation": PresentationPhase.VALIDATING,
        "generation": PresentationPhase.GENERATING,
    }.get(stage.lower(), PresentationPhase.RESEARCHING)


def reduce_event(state: PresentationState, event: ResearchEvent) -> PresentationState:
    """Apply one event; duplicate and late events are ignored."""
    sequence = event.meta.sequence
    if sequence <= state.latest_sequence:
        return state
    state = replace(state, latest_sequence=sequence, last_event_type=event.type)

    if isinstance(event, RunStarted):
        return replace(
            state,
            phase=PresentationPhase.STARTING,
            run_id=event.meta.run_id,
            query=event.query,
        )
    if isinstance(event, StageStarted):
        activities = dict(state.activities)
        if state.current_operation:
            activities = {
                key: replace(activity, status="completed")
                if activity.label == state.current_operation
                and activity.status == "running"
                else activity
                for key, activity in activities.items()
            }
        activities[event.stage] = ActivityState(event.label)
        return replace(
            state,
            phase=_phase_for_stage(event.stage),
            current_operation=event.label,
            activities=activities,
        )
    if isinstance(event, ModelRequestStarted):
        activities = dict(state.activities)
        activities["model"] = ActivityState("Contacting model")
        return replace(
            state,
            phase=PresentationPhase.GENERATING,
            current_operation="Contacting model",
            activities=activities,
        )
    if isinstance(event, ProviderAttemptStarted):
        activities = dict(state.activities)
        activities["provider"] = ActivityState(
            "Contacting Hive", detail=f"attempt {event.attempt}"
        )
        return replace(
            state,
            phase=PresentationPhase.GENERATING,
            current_operation="Contacting Hive",
            activities=activities,
        )
    if isinstance(event, ProviderRetrying):
        activities = dict(state.activities)
        activities["provider"] = ActivityState(
            "Retrying Hive",
            detail=f"{event.reason} · {event.delay_ms / 1000:.1f}s",
        )
        return replace(
            state,
            phase=PresentationPhase.GENERATING,
            current_operation="Retrying Hive",
            activities=activities,
        )
    if isinstance(event, ProviderStreamStarted):
        activities = dict(state.activities)
        activities["provider"] = ActivityState(
            "Streaming response", detail=f"first byte {event.first_byte_ms / 1000:.1f}s"
        )
        return replace(
            state,
            phase=PresentationPhase.GENERATING,
            current_operation="Streaming response",
            activities=activities,
        )
    if isinstance(event, ProviderCompleted | ProviderFailed):
        activities = dict(state.activities)
        if isinstance(event, ProviderCompleted):
            detail = f"{event.attempts} attempt(s) · {event.duration_ms / 1000:.1f}s"
            status = "completed"
        else:
            detail = event.message
            status = "failed"
        activities["provider"] = ActivityState("Hive provider", status, detail)
        return replace(state, activities=activities, current_operation=None)
    if isinstance(event, ToolProgress):
        key = f"tool:{event.tool_id}"
        activities = dict(state.activities)
        activity = activities.get(key)
        if activity:
            activities[key] = replace(activity, detail=event.message)
        return replace(state, activities=activities, current_operation=event.message)
    if isinstance(event, StageCompleted | StageFailed):
        activities = dict(state.activities)
        activity = activities.get(event.stage)
        if activity:
            activities[event.stage] = replace(
                activity,
                status="failed" if isinstance(event, StageFailed) else "completed",
                detail=event.message
                if isinstance(event, StageFailed)
                else event.detail,
            )
        current = (
            None
            if activity and state.current_operation == activity.label
            else state.current_operation
        )
        return replace(state, activities=activities, current_operation=current)
    if isinstance(event, ToolStarted):
        activities = dict(state.activities)
        tool_key = event.tool_id or event.tool
        activities[f"tool:{tool_key}"] = ActivityState(event.tool, detail=event.detail)
        return replace(
            state,
            phase=PresentationPhase.RESEARCHING,
            current_operation=event.tool,
            active_tools=(*state.active_tools, tool_key),
            activities=activities,
        )
    if isinstance(event, ToolCompleted | ToolFailed):
        tool_key = event.tool_id or event.tool
        key = f"tool:{tool_key}"
        activities = dict(state.activities)
        activity = activities.get(key)
        if activity is None and isinstance(event, ToolFailed):
            activity = ActivityState(event.tool)
        if activity:
            activities[key] = replace(
                activity,
                status="failed" if isinstance(event, ToolFailed) else "completed",
                detail=event.message if isinstance(event, ToolFailed) else event.detail,
            )
        active_tools = tuple(tool for tool in state.active_tools if tool != tool_key)
        current = (
            None if state.current_operation == event.tool else state.current_operation
        )
        return replace(
            state,
            activities=activities,
            active_tools=active_tools,
            current_operation=current,
        )
    if isinstance(event, TextDelta):
        return replace(
            state,
            phase=PresentationPhase.GENERATING,
            response_text=state.response_text + event.text,
            response_delta_count=state.response_delta_count + 1,
        )
    if isinstance(event, SourcesUpdated):
        return replace(state, sources=list(event.sources))
    if isinstance(event, ApprovalRequested):
        return replace(state, phase=PresentationPhase.WAITING_FOR_APPROVAL)
    if isinstance(event, ClarificationRequested):
        return replace(state, phase=PresentationPhase.WAITING_FOR_CLARIFICATION)
    if isinstance(event, ApprovalResolved):
        return replace(state, phase=PresentationPhase.RESEARCHING)
    if isinstance(event, RunCompleted):
        activities = {
            key: ActivityState(item.label, "completed", item.detail)
            if item.status == "running"
            else item
            for key, item in state.activities.items()
        }
        return replace(
            state,
            phase=PresentationPhase.COMPLETE,
            terminal_status=event.terminal_status,
            current_operation=None,
            active_tools=(),
            activities=activities,
        )
    if isinstance(event, RunFailed):
        return replace(
            state,
            phase=PresentationPhase.FAILED,
            error=event.message,
            terminal_status="failed",
            current_operation=None,
            active_tools=(),
        )
    if isinstance(event, RunCancelled):
        return replace(
            state,
            phase=PresentationPhase.CANCELLED,
            terminal_status="cancelled",
            current_operation=None,
            active_tools=(),
        )
    return state
