from pydantic import BaseModel
from typing import Optional, Any


class ChatResponse(BaseModel):
    content: str
    role: str = "assistant"
    model: str
    total_duration: Optional[int] = None


class StreamEvent(BaseModel):
    """
    Structure for SSE events.
    Can be 'token', 'error', 'done', or 'tool_call'.
    """

    event: str  # token, done, error
    data: Any  # The actual payload
