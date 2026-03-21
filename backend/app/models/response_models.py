from pydantic import BaseModel
from typing import Optional, Any


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
    status: str  # running, completed, error
    input: str
    output: Optional[str] = None


class StreamEvent(BaseModel):
    """
    Structure for SSE events.
    Can be 'token', 'error', 'done', 'tool_call', or 'tool_status'.
    """

    event: str
    data: Any  # The actual payload
