from pydantic import BaseModel
from typing import Optional, Any, Literal, Union, Dict


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
    Can be 'token', 'error', 'done', 'tool_call', or 'tool_status'.
    """

    event: Literal["token", "error", "done", "tool_call", "tool_status"]
    data: Union[ToolStatus, ChatResponse, str, Dict[str, Any]]
