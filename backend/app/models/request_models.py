from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal, Dict, Any


class Message(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: Optional[str] = None
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class ChatRequest(BaseModel):
    messages: List[Message]
    model: Optional[str] = None
    stream: bool = True
    max_tokens: Optional[int] = None
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    tools: Optional[List[Dict[str, Any]]] = None

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: List[Message]) -> List[Message]:
        if not v:
            raise ValueError("Messages list cannot be empty")
        return v
