"""Typed events shared by the research engine and presentation clients."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class EventMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: UUID
    run_id: UUID
    conversation_id: UUID
    sequence: int = Field(ge=1)
    occurred_at: datetime


class RunStarted(BaseModel):
    type: Literal["run.started"] = "run.started"
    meta: EventMeta
    query: str


class RunCompleted(BaseModel):
    type: Literal["run.completed"] = "run.completed"
    meta: EventMeta
    terminal_status: str
    duration_ms: float | None = None
    artifact_path: str | None = None


class RunFailed(BaseModel):
    type: Literal["run.failed"] = "run.failed"
    meta: EventMeta
    message: str
    category: str = "internal"


class RunCancelled(BaseModel):
    type: Literal["run.cancelled"] = "run.cancelled"
    meta: EventMeta
    reason: str = "cancelled by user"


class StageStarted(BaseModel):
    type: Literal["stage.started"] = "stage.started"
    meta: EventMeta
    stage: str
    label: str


class StageCompleted(BaseModel):
    type: Literal["stage.completed"] = "stage.completed"
    meta: EventMeta
    stage: str
    label: str
    detail: str | None = None


class StageFailed(BaseModel):
    type: Literal["stage.failed"] = "stage.failed"
    meta: EventMeta
    stage: str
    label: str
    message: str


class ToolStarted(BaseModel):
    type: Literal["tool.started"] = "tool.started"
    meta: EventMeta
    tool: str
    tool_id: str | None = None
    detail: str | None = None


class ToolCompleted(BaseModel):
    type: Literal["tool.completed"] = "tool.completed"
    meta: EventMeta
    tool: str
    tool_id: str | None = None
    detail: str | None = None
    duration_ms: float | None = None


class ToolFailed(BaseModel):
    type: Literal["tool.failed"] = "tool.failed"
    meta: EventMeta
    tool: str
    tool_id: str | None = None
    message: str


class TextDelta(BaseModel):
    type: Literal["response.delta"] = "response.delta"
    meta: EventMeta
    text: str


class ModelRequestStarted(BaseModel):
    type: Literal["model.request.started"] = "model.request.started"
    meta: EventMeta
    model: str
    round: int


class ModelResponseCompleted(BaseModel):
    type: Literal["model.response.completed"] = "model.response.completed"
    meta: EventMeta
    round: int
    has_tool_calls: bool = False


class ProviderAttemptStarted(BaseModel):
    type: Literal["provider.attempt.started"] = "provider.attempt.started"
    meta: EventMeta
    provider: str = "hive"
    attempt: int


class ProviderRetrying(BaseModel):
    type: Literal["provider.retrying"] = "provider.retrying"
    meta: EventMeta
    provider: str = "hive"
    attempt: int
    status_code: int | None = None
    delay_ms: float
    reason: str


class ProviderStreamStarted(BaseModel):
    type: Literal["provider.stream.started"] = "provider.stream.started"
    meta: EventMeta
    provider: str = "hive"
    attempt: int
    first_byte_ms: float


class ProviderCompleted(BaseModel):
    type: Literal["provider.completed"] = "provider.completed"
    meta: EventMeta
    provider: str = "hive"
    attempts: int
    duration_ms: float
    first_token_ms: float | None = None


class ProviderFailed(BaseModel):
    type: Literal["provider.failed"] = "provider.failed"
    meta: EventMeta
    provider: str = "hive"
    attempts: int
    phase: str
    message: str
    status_code: int | None = None


class ToolProgress(BaseModel):
    type: Literal["tool.progress"] = "tool.progress"
    meta: EventMeta
    tool: str
    tool_id: str
    message: str


class ContextCompacted(BaseModel):
    type: Literal["context.compacted"] = "context.compacted"
    meta: EventMeta
    compacted_messages: int
    estimated_tokens: int


class SkillSelected(BaseModel):
    type: Literal["skill.selected"] = "skill.selected"
    meta: EventMeta
    skill_id: str
    version: str
    package_hash: str


class SourcesUpdated(BaseModel):
    type: Literal["sources.updated"] = "sources.updated"
    meta: EventMeta
    sources: list[dict[str, str]]


class ApprovalRequested(BaseModel):
    type: Literal["approval.requested"] = "approval.requested"
    meta: EventMeta
    prompt: str
    details: str | None = None


class ApprovalResolved(BaseModel):
    type: Literal["approval.resolved"] = "approval.resolved"
    meta: EventMeta
    decision: Literal["approved", "rejected", "revised"]


class ClarificationRequested(BaseModel):
    type: Literal["clarification.requested"] = "clarification.requested"
    meta: EventMeta
    prompt: str


ResearchEvent = Annotated[
    RunStarted
    | RunCompleted
    | RunFailed
    | RunCancelled
    | StageStarted
    | StageCompleted
    | StageFailed
    | ToolStarted
    | ToolCompleted
    | ToolFailed
    | TextDelta
    | ModelRequestStarted
    | ModelResponseCompleted
    | ProviderAttemptStarted
    | ProviderRetrying
    | ProviderStreamStarted
    | ProviderCompleted
    | ProviderFailed
    | ToolProgress
    | ContextCompacted
    | SkillSelected
    | SourcesUpdated
    | ApprovalRequested
    | ApprovalResolved
    | ClarificationRequested,
    Field(discriminator="type"),
]

EventType = TypeVar("EventType", bound=BaseModel)


class EventFactory:
    """Assign one run identity and a monotonic sequence to emitted events."""

    def __init__(
        self, conversation_id: UUID, run_id: UUID | None = None, sequence: int = 0
    ) -> None:
        self.conversation_id = conversation_id
        self.run_id = run_id or uuid4()
        self._sequence = sequence

    def make(self, event_type: type[EventType], **payload: object) -> EventType:
        self._sequence += 1
        return event_type(
            meta=EventMeta(
                event_id=uuid4(),
                run_id=self.run_id,
                conversation_id=self.conversation_id,
                sequence=self._sequence,
                occurred_at=datetime.now(UTC),
            ),
            **payload,
        )
