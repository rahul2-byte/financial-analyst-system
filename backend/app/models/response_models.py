from pydantic import BaseModel
from typing import Optional, Any, Literal, List


class ChatResponse(BaseModel):
    content: str
    role: str = "assistant"
    model: str
    total_duration: Optional[int] = None


class ToolStatus(BaseModel):
    tool_id: str
    step_number: int
    agent: str
    tool_name: str
    status: Literal["running", "completed", "error"]
    input: str
    output: Optional[str] = None


class StreamEvent(BaseModel):
    """
    Structure for SSE events.
    Aligned with frontend (hooks/useChat.ts and state/chat/messageReducer.ts).
    """

    type: Literal["text_delta", "error", "done", "tool_status", "status", "chart"]
    content: Optional[str] = None
    message: Optional[str] = None
    tool_id: Optional[str] = None
    step_number: Optional[int] = None
    agent: Optional[str] = None
    tool_name: Optional[str] = None
    status: Optional[Literal["running", "completed", "error"]] = None
    input: Optional[str] = None
    output: Optional[str] = None
    title: Optional[str] = None
    chartType: Optional[str] = None
    data: Optional[Any] = None
    xAxisKey: Optional[str] = None
    seriesKeys: Optional[List[str]] = None
