"""Provider-frame conversion for AgentLoop model streaming."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.core.agent_loop.model_events import merge_chunk_tool_calls, sanitize_tool_calls
from app.core.observability import observe
from app.events.models import (
    EventFactory,
    ProviderAttemptStarted,
    ProviderCompleted,
    ProviderFailed,
    ProviderRetrying,
    ProviderStreamStarted,
    TextDelta,
    TokenUsage,
)
from app.models.request_models import Message


class ModelStreaming:
    """Turn provider frames into typed events and one assistant message."""

    def __init__(
        self,
        client: Any,
        model: str,
        max_tokens: int,
        tool_definitions: Callable[[], list[dict[str, Any]]],
        *,
        publish_reports: bool = False,
        report_max_tokens: int = 32768,
        report_repair_max_tokens: int = 8192,
        report_repair_timeout_seconds: float = 120.0,
        structured_output: bool | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._tool_definitions = tool_definitions
        self._publish_reports = publish_reports
        self._structured_output = (
            publish_reports if structured_output is None else structured_output
        )
        self._report_max_tokens = report_max_tokens
        self._report_repair_max_tokens = report_repair_max_tokens
        self._report_repair_timeout_seconds = report_repair_timeout_seconds

    @observe("llm.round", as_type="llm_round")
    async def stream(
        self, messages: list[Message], factory: EventFactory, round_number: int
    ) -> AsyncIterator[Any]:
        text: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        usage: TokenUsage | None = None
        is_repair = self._structured_output and any(
            message.prompt_key
            in {"publication.report_repair", "publication.lookup_repair"}
            for message in messages
        )
        async for event in self._client.generate_stream(
            messages,
            self._model,
            tools=self._tool_definitions(),
            max_tokens=(
                self._report_repair_max_tokens
                if is_repair
                else self._report_max_tokens
                if self._publish_reports
                and any(message.role == "tool" for message in messages)
                else self._max_tokens
                if any(message.role == "tool" for message in messages)
                else self._report_max_tokens
                if self._publish_reports and round_number > 1
                else self._max_tokens
                if round_number > 1
                else min(self._max_tokens, 1024)
            ),
            temperature=0.1,
            run_id=str(factory.run_id),
            conversation_id=str(factory.conversation_id),
            timeout_seconds=(
                self._report_repair_timeout_seconds if is_repair else None
            ),
        ):
            event_name = event.get("event")
            if event_name == "provider_attempt_started":
                data = event.get("data", {})
                yield factory.make(
                    ProviderAttemptStarted,
                    provider=str(data.get("provider", "hive")),
                    attempt=int(data.get("attempt", 1)),
                )
            elif event_name == "provider_retrying":
                data = event.get("data", {})
                yield factory.make(
                    ProviderRetrying,
                    provider=str(data.get("provider", "hive")),
                    attempt=int(data.get("attempt", 1)),
                    status_code=data.get("status_code"),
                    delay_ms=float(data.get("delay_ms", 0)),
                    reason=str(data.get("reason", "transient provider failure")),
                )
            elif event_name == "provider_stream_started":
                data = event.get("data", {})
                yield factory.make(
                    ProviderStreamStarted,
                    provider=str(data.get("provider", "hive")),
                    attempt=int(data.get("attempt", 1)),
                    first_byte_ms=float(data.get("first_byte_ms", 0)),
                )
            elif event_name == "provider_completed":
                data = event.get("data", {})
                yield factory.make(
                    ProviderCompleted,
                    provider=str(data.get("provider", "hive")),
                    attempts=int(data.get("attempts", 1)),
                    duration_ms=float(data.get("duration_ms", 0)),
                    first_token_ms=data.get("first_token_ms"),
                    model_id=data.get("model_id"),
                    usage=usage or _parse_usage(data.get("usage")),
                )
            elif event_name == "provider_failed":
                data = event.get("data", {})
                yield factory.make(
                    ProviderFailed,
                    provider=str(data.get("provider", "hive")),
                    attempts=int(data.get("attempts", 1)),
                    phase=str(data.get("phase", "unknown")),
                    status_code=data.get("status_code"),
                    message=str(data.get("message", "Hive provider failed")),
                    duration_ms=data.get("duration_ms"),
                    timeout=data.get("timeout"),
                    partial_output=data.get("partial_output"),
                    model_id=data.get("model_id"),
                    usage=usage or _parse_usage(data.get("usage")),
                )
            elif event_name == "usage":
                usage = _parse_usage(event.get("data"))
            elif event_name == "token":
                usage = _parse_usage(event.get("usage")) or usage
                async for output in self._emit_text(
                    str(event.get("data", "")), factory, text
                ):
                    yield output
                merge_chunk_tool_calls(calls, event.get("chunk"))
            elif event_name == "chunk":
                usage = _parse_usage(event.get("usage")) or usage
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
            yield factory.make(TextDelta, text=part)
            await asyncio.sleep(0)


def _parse_usage(value: Any) -> TokenUsage | None:
    if not isinstance(value, dict) or not value:
        return None
    try:
        return TokenUsage.model_validate({**value, "verified": True})
    except ValueError:
        return None
