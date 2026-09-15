from typing import Any, Literal

from pydantic import BaseModel


class ChatResponse(BaseModel):
    content: str
    role: str = "assistant"
    model: str
    total_duration: int | None = None


class ToolStatus(BaseModel):
    tool_id: str
    step_number: int
    agent: str
    tool_name: str
    status: Literal["running", "completed", "error"]
    input: str
    output: str | None = None


class StreamEvent(BaseModel):
    """
    Structure for SSE events.
    Shared streaming response contract for API and CLI clients.
    """

    type: Literal[
        "text_delta",
        "error",
        "done",
        "tool_status",
        "status",
        "chart",
        "final_payload",
        "clarification_required",
        "plan_proposed",
        "approval_required",
        "approval_recorded",
        "scope_escalation_required",
        "manual_review_required",
        "run_cancelled",
    ]
    content: str | None = None
    message: str | None = None
    tool_id: str | None = None
    step_number: int | None = None
    agent: str | None = None
    tool_name: str | None = None
    status: Literal["running", "completed", "error"] | None = None
    input: str | None = None
    output: str | None = None
    title: str | None = None
    chartType: str | None = None
    data: Any | None = None
    xAxisKey: str | None = None
    seriesKeys: list[str] | None = None
    payload: Any | None = None
