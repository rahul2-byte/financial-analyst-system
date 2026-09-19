from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Message(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str = Field(min_length=0, max_length=8000)
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=1)
    model: str | None = None
    stream: bool = True
    max_tokens: int | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    tools: list[dict[str, Any]] | None = None
    publish_report: bool = False
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,128}$")

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: list[Message]) -> list[Message]:
        if not v:
            raise ValueError("Messages list cannot be empty")
        return v

    @field_validator("messages")
    @classmethod
    def reject_untrusted_tool_messages(cls, messages: list[Message]) -> list[Message]:
        if any(message.role != "user" for message in messages):
            raise ValueError("HTTP chat accepts one new user message per request")
        return messages
