from typing import Any, Literal

from pydantic import BaseModel, Field

MAX_MESSAGE_CONTENT_CHARS = 131_072


class Message(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str = Field(min_length=0, max_length=MAX_MESSAGE_CONTENT_CHARS)
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    prompt_key: str | None = Field(default=None, exclude=True)
