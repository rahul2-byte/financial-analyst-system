from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from app.models.request_models import Message


class AnthropicService:
    """Small streaming Anthropic Messages adapter for no-tool model routes."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.anthropic.com",
        model: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = model
        self._client = client or httpx.AsyncClient()

    async def aclose(self) -> None:
        if not self._client.is_closed:
            await self._client.aclose()

    def generate_stream(
        self, messages: list[Message], model: str, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        return self._stream(messages, model, **kwargs)

    async def _stream(
        self, messages: list[Message], model: str, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")
        system = "\n\n".join(
            message.content for message in messages if message.role == "system"
        )
        payload: dict[str, Any] = {
            "model": self.default_model if model == "reasoning" else model,
            "max_tokens": int(kwargs.get("max_tokens", 8192)),
            "stream": True,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
                if message.role in {"user", "assistant"}
            ],
        }
        if system:
            payload["system"] = system
        async with self._client.stream(
            "POST",
            f"{self.base_url}/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data:
                    continue
                event = json.loads(data)
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("text"):
                        yield {"event": "token", "data": delta["text"]}
                elif event.get("type") == "message_delta" and event.get("usage"):
                    yield {"event": "usage", "data": event["usage"]}
                elif event.get("type") == "message_stop":
                    yield {"event": "done", "data": "[DONE]"}

    async def generate(self, messages: list[Message], model: str, **kwargs: Any) -> str:
        parts: list[str] = []
        async for event in self.generate_stream(messages, model, **kwargs):
            if event.get("event") == "token":
                parts.append(str(event["data"]))
        return "".join(parts)

    async def generate_message(
        self, messages: list[Message], model: str, **kwargs: Any
    ) -> Message:
        return Message(
            role="assistant",
            content=await self.generate(messages, model, **kwargs),
        )

    async def check_health(self) -> bool:
        return bool(self.api_key)
