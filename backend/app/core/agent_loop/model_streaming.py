"""Provider-frame conversion for AgentLoop model streaming."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.core.agent_loop.model_events import merge_chunk_tool_calls, sanitize_tool_calls
from app.events.models import (
    EventFactory,
    ProviderAttemptStarted,
    ProviderCompleted,
    ProviderFailed,
    ProviderRetrying,
    ProviderStreamStarted,
    TextDelta,
)
from app.models.request_models import Message


class ModelStreaming:
    """Turn provider frames into typed events and one assistant message."""

    def __init__(
        self,
        client: Any,
        model: str,
        max_tokens: int,
        publish_reports: bool,
        tool_definitions: Callable[[], list[dict[str, Any]]],
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._publish_reports = publish_reports
        self._tool_definitions = tool_definitions

    async def stream(
        self, messages: list[Message], factory: EventFactory, round_number: int
    ) -> AsyncIterator[Any]:
        del round_number
        text: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        async for event in self._client.generate_stream(
            messages,
            self._model,
            tools=self._tool_definitions(),
            max_tokens=(
                self._max_tokens
                if any(message.role == "tool" for message in messages)
                else min(self._max_tokens, 512)
            ),
            temperature=0.1,
        ):
            event_name = event.get("event")
            if event_name == "provider_attempt_started":
                yield factory.make(
                    ProviderAttemptStarted,
                    attempt=int(event.get("data", {}).get("attempt", 1)),
                )
            elif event_name == "provider_retrying":
                data = event.get("data", {})
                yield factory.make(
                    ProviderRetrying,
                    attempt=int(data.get("attempt", 1)),
                    status_code=data.get("status_code"),
                    delay_ms=float(data.get("delay_ms", 0)),
                    reason=str(data.get("reason", "transient provider failure")),
                )
            elif event_name == "provider_stream_started":
                data = event.get("data", {})
                yield factory.make(
                    ProviderStreamStarted,
                    attempt=int(data.get("attempt", 1)),
                    first_byte_ms=float(data.get("first_byte_ms", 0)),
                )
            elif event_name == "provider_completed":
                data = event.get("data", {})
                yield factory.make(
                    ProviderCompleted,
                    attempts=int(data.get("attempts", 1)),
                    duration_ms=float(data.get("duration_ms", 0)),
                    first_token_ms=data.get("first_token_ms"),
                )
            elif event_name == "provider_failed":
                data = event.get("data", {})
                yield factory.make(
                    ProviderFailed,
                    attempts=int(data.get("attempts", 1)),
                    phase=str(data.get("phase", "unknown")),
                    status_code=data.get("status_code"),
                    message=str(data.get("message", "Hive provider failed")),
                )
            elif event_name == "token":
                async for output in self._emit_text(
                    str(event.get("data", "")), factory, text
                ):
                    yield output
                merge_chunk_tool_calls(calls, event.get("chunk"))
            elif event_name == "chunk":
                payload = event.get("data")
                if isinstance(payload, dict):
                    choices = payload.get("choices", [])
                    delta = choices[0].get("delta", {}) if choices else {}
                    content = delta.get("content") if isinstance(delta, dict) else None
                    if content:
                        async for output in self._emit_text(
                            str(content), factory, text
                        ):
                            yield output
                merge_chunk_tool_calls(calls, payload)
        tool_calls = (
            sanitize_tool_calls([calls[index] for index in sorted(calls)]) or None
        )
        yield Message(role="assistant", content="".join(text), tool_calls=tool_calls)

    async def _emit_text(
        self, chunk: str, factory: EventFactory, text: list[str]
    ) -> AsyncIterator[TextDelta]:
        for offset in range(0, len(chunk), 64):
            part = chunk[offset : offset + 64]
            if not part:
                continue
            text.append(part)
            if not self._publish_reports:
                yield factory.make(TextDelta, text=part)
            await asyncio.sleep(0)
