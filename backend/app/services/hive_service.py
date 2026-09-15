from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import httpx
from app.config import settings
from app.core.circuit_breaker import CircuitBreaker
from app.core.model_stream import get_public_token_sink
from app.models.request_models import Message
from app.services.llm_interface import LLMServiceInterface

logger = logging.getLogger(__name__)


class HiveProviderError(RuntimeError):
    """A provider or stream protocol failure from Hive."""


def _retryable_status(status_code: int) -> bool:
    return status_code in {408, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class HiveRetryPolicy:
    max_retries: int
    total_budget_seconds: float
    backoff_base_seconds: float
    backoff_cap_seconds: float
    retry_after_cap_seconds: float = 10.0
    read_timeout_seconds: float = 20.0


def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def merge_tool_call_deltas(
    calls: dict[int, dict[str, Any]], deltas: list[dict[str, Any]]
) -> None:
    """Merge OpenAI-compatible streamed tool-call fragments in place."""
    for delta in deltas:
        index = delta.get("index")
        if not isinstance(index, int):
            continue
        call = calls.setdefault(index, {"index": index})
        for key in ("id", "type"):
            value = delta.get(key)
            if value:
                call[key] = value
        function = delta.get("function")
        if not isinstance(function, dict):
            continue
        target = call.setdefault("function", {})
        if not isinstance(target, dict):
            target = {}
            call["function"] = target
        if function.get("name"):
            target["name"] = function["name"]
        if function.get("arguments"):
            target["arguments"] = str(target.get("arguments", "")) + str(
                function["arguments"]
            )


class HiveService(LLMServiceInterface):
    """OpenAI-compatible streaming client for Hive GLM-5.3-Flash."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        retry_policy: HiveRetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.base_url = str(settings.HIVE_BASE_URL).rstrip("/")
        self.api_key = settings.HIVE_API_KEY
        self.default_model = str(settings.HIVE_MODEL)
        self.last_telemetry: dict[str, Any] = {}
        self.retry_policy = retry_policy or HiveRetryPolicy(
            max_retries=settings.HIVE_MAX_RETRIES,
            total_budget_seconds=settings.HIVE_TIMEOUT,
            backoff_base_seconds=settings.HIVE_BACKOFF_BASE,
            backoff_cap_seconds=settings.HIVE_BACKOFF_CAP,
        )
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=settings.HIVE_CONNECT_TIMEOUT,
                pool=settings.HIVE_POOL_TIMEOUT,
                write=settings.HIVE_WRITE_TIMEOUT,
                read=settings.HIVE_READ_TIMEOUT,
            ),
            limits=httpx.Limits(
                max_connections=settings.HTTP_POOL_MAX_CONNECTIONS,
                max_keepalive_connections=settings.HTTP_POOL_MAX_KEEPALIVE_CONNECTIONS,
            ),
        )
        self._circuit = circuit_breaker or CircuitBreaker(
            "hive",
            failure_threshold=settings.HIVE_CIRCUIT_FAILURE_THRESHOLD,
            recovery_timeout=settings.HIVE_CIRCUIT_RECOVERY_TIMEOUT,
        )

    async def aclose(self) -> None:
        if not self._client.is_closed:
            await self._client.aclose()

    @staticmethod
    def parse_sse_line(line: str) -> dict[str, Any] | None:
        if not line.startswith("data:"):
            return None
        payload = line[5:].strip()
        if payload == "[DONE]":
            return {"event": "done", "data": "[DONE]"}
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise HiveProviderError(f"malformed SSE payload: {exc}") from exc
        if not isinstance(chunk, dict):
            raise HiveProviderError("malformed SSE payload: expected object")
        usage = chunk.get("usage")
        choices = chunk.get("choices", [])
        if isinstance(usage, dict) and not choices:
            return {"event": "usage", "data": usage}
        delta = choices[0].get("delta", {}) if choices and isinstance(choices[0], dict) else {}
        event: dict[str, Any] = {"event": "chunk", "data": chunk}
        if isinstance(usage, dict):
            event["usage"] = usage
        if isinstance(delta, dict) and delta.get("content"):
            event["event"] = "token"
            event["data"] = delta["content"]
            # Preserve tool-call fragments when a provider sends content and
            # tool metadata in the same OpenAI-compatible chunk.
            if isinstance(delta.get("tool_calls"), list):
                event["chunk"] = chunk
        return event

    def _model(self, model: str) -> str:
        return self.default_model if model == "reasoning" else model

    async def _stream_request(
        self, messages: list[Message], model: str, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        if not self.api_key:
            raise HiveProviderError("HIVE_API_KEY is not configured")
        if not self._circuit.can_execute():
            from app.core.circuit_breaker import CircuitBreakerOpen

            raise CircuitBreakerOpen("Circuit 'hive' is open")
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": self._model(model),
            "messages": [message.model_dump(exclude_none=True) for message in messages],
            "stream": True,
            "max_tokens": kwargs.get("max_tokens", settings.HIVE_MAX_OUTPUT_TOKENS),
            "temperature": kwargs.get("temperature", 0.7),
        }
        if kwargs.get("tools"):
            payload["tools"] = kwargs["tools"]
        retries = 0
        request_deadline = started + self.retry_policy.total_budget_seconds
        streamed_token_count = 0
        reasoning_chunk_count = 0
        reasoning_chars = 0
        public_token_chars = 0
        emitted_tool_call = False
        while True:
            first_token_at: float | None = None
            usage: dict[str, Any] = {}
            attempt = retries + 1
            yield {
                "event": "provider_attempt_started",
                "data": {"attempt": attempt, "provider": "hive"},
            }
            try:
                remaining = request_deadline - time.perf_counter()
                if remaining <= 0:
                    raise HiveProviderError("Hive request budget exhausted")
                # The client's read timeout is only a per-read limit. The
                # request budget must also cap the whole attempt, otherwise a
                # stalled SSE stream can run past the configured deadline.
                async with asyncio.timeout(remaining):
                    async with self._client.stream(
                            "POST",
                            f"{self.base_url}/chat/completions",
                            json=payload,
                            headers={
                                "Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json",
                                "Accept": "text/event-stream",
                            },
                        ) as response:
                            if response.status_code != 200:
                                body = (await response.aread()).decode(errors="replace")
                                if (
                                    _retryable_status(response.status_code)
                                    and retries < self.retry_policy.max_retries
                                ):
                                    delay = _retry_delay(
                                        retries,
                                        response.headers.get("Retry-After"),
                                        self.retry_policy,
                                    )
                                    if time.perf_counter() + delay >= request_deadline:
                                        raise HiveProviderError(
                                            "Hive request budget exhausted during retry"
                                        )
                                    retries += 1
                                    yield {
                                        "event": "provider_retrying",
                                        "data": {
                                            "attempt": attempt,
                                            "status_code": response.status_code,
                                            "delay_ms": round(delay * 1000, 2),
                                            "reason": f"HTTP {response.status_code}",
                                        },
                                    }
                                    await asyncio.sleep(delay)
                                    continue
                                yield {
                                    "event": "provider_failed",
                                    "data": {
                                        "attempts": attempt,
                                        "phase": "http",
                                        "status_code": response.status_code,
                                        "message": f"Hive HTTP {response.status_code}",
                                    },
                                }
                                raise HiveProviderError(
                                    f"Hive HTTP {response.status_code}: {body[:500]}"
                                )
                            saw_done = False
                            stream_started_emitted = False
                            lines = response.aiter_lines()
                            while True:
                                try:
                                    line = await asyncio.wait_for(
                                        lines.__anext__(),
                                        timeout=self.retry_policy.read_timeout_seconds,
                                    )
                                except StopAsyncIteration:
                                    break
                                if not stream_started_emitted:
                                    stream_started_emitted = True
                                    yield {
                                        "event": "provider_stream_started",
                                        "data": {
                                            "attempt": attempt,
                                            "first_byte_ms": round(
                                                (time.perf_counter() - started) * 1000, 2
                                            ),
                                        },
                                    }
                                parsed = self.parse_sse_line(line)
                                if not parsed:
                                    continue
                                if parsed["event"] == "usage":
                                    usage = parsed["data"]
                                    yield parsed
                                elif parsed["event"] == "token":
                                    first_token_at = first_token_at or time.perf_counter()
                                    streamed_token_count += 1
                                    public_token_chars += len(str(parsed["data"]))
                                    logger.debug(
                                        "Hive SSE token chunk received",
                                        extra={
                                            "chunk_index": streamed_token_count,
                                            "chunk_chars": len(str(parsed["data"])),
                                        },
                                    )
                                    sink = get_public_token_sink()
                                    if sink:
                                        await sink(str(parsed["data"]))
                                        # Let the orchestrator and terminal consume this
                                        # chunk before the provider reads the next one.
                                        await asyncio.sleep(0)
                                    yield parsed
                                elif parsed["event"] == "done":
                                    saw_done = True
                                    yield parsed
                                    break
                                elif parsed["event"] == "chunk":
                                    if isinstance(parsed.get("usage"), dict):
                                        usage = parsed["usage"]
                                    choices = parsed["data"].get("choices", [])
                                    delta = choices[0].get("delta", {}) if choices else {}
                                    if isinstance(delta, dict) and delta.get("reasoning_content"):
                                        reasoning_chunk_count += 1
                                        reasoning_chars += len(str(delta["reasoning_content"]))
                                    if isinstance(delta, dict) and delta.get("tool_calls"):
                                        emitted_tool_call = True
                                    yield parsed
                            if not saw_done:
                                raise HiveProviderError("incomplete Hive SSE stream")
                self.last_telemetry = {
                    "model_id": self._model(model),
                    "request_latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "first_token_latency_ms": round((first_token_at - started) * 1000, 2) if first_token_at else None,
                    "retry_count": retries,
                    "provider_status": "completed",
                    "streamed_token_count": streamed_token_count,
                    "public_token_chars": public_token_chars,
                    "reasoning_chunk_count": reasoning_chunk_count,
                    "reasoning_chars": reasoning_chars,
                    "usage": usage,
                }
                self._circuit.record_success()
                yield {
                    "event": "provider_completed",
                    "data": {
                        "attempts": attempt,
                        "duration_ms": self.last_telemetry["request_latency_ms"],
                        "first_token_ms": self.last_telemetry[
                            "first_token_latency_ms"
                        ],
                    },
                }
                return
            except (TimeoutError, httpx.TimeoutException, httpx.TransportError) as exc:
                if streamed_token_count or emitted_tool_call:
                    raise HiveProviderError(
                        "Hive transport failed after the response had started"
                    ) from exc
                if retries < self.retry_policy.max_retries:
                    delay = _retry_delay(retries, None, self.retry_policy)
                    if time.perf_counter() + delay >= request_deadline:
                        raise HiveProviderError(
                            f"Hive transport failure: {exc}"
                        ) from exc
                    retries += 1
                    yield {
                        "event": "provider_retrying",
                        "data": {
                            "attempt": attempt,
                            "delay_ms": round(delay * 1000, 2),
                            "reason": type(exc).__name__,
                        },
                    }
                    await asyncio.sleep(delay)
                    continue
                yield {
                    "event": "provider_failed",
                    "data": {
                        "attempts": attempt,
                        "phase": "transport",
                        "message": type(exc).__name__,
                    },
                }
                raise HiveProviderError(f"Hive transport failure: {exc}") from exc
            except HiveProviderError:
                self._circuit.record_failure()
                raise
    def generate_stream(
        self, messages: list[Message], model: str, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        async def generator() -> AsyncGenerator[dict[str, Any], None]:
            async for event in self._stream_request(messages, model, **kwargs):
                public = {"event": event["event"], "data": event["data"]}
                if "chunk" in event:
                    public["chunk"] = event["chunk"]
                if "usage" in event:
                    public["usage"] = event["usage"]
                yield public

        return generator()

    async def generate(self, messages: list[Message], model: str, **kwargs: Any) -> str:
        parts: list[str] = []
        async for event in self._stream_request(messages, model, **kwargs):
            if event["event"] == "token":
                parts.append(str(event["data"]))
        return "".join(parts)

    async def generate_message(
        self, messages: list[Message], model: str, **kwargs: Any
    ) -> Message:
        parts: list[str] = []
        tool_calls_by_index: dict[int, dict[str, Any]] = {}
        async for event in self._stream_request(messages, model, **kwargs):
            if event["event"] == "token":
                parts.append(str(event["data"]))
            elif event["event"] == "chunk":
                choices = event["data"].get("choices", [])
                delta = choices[0].get("delta", {}) if choices else {}
                if isinstance(delta, dict) and delta.get("tool_calls"):
                    merge_tool_call_deltas(tool_calls_by_index, delta["tool_calls"])
        return Message(
            role="assistant",
            content="".join(parts),
            tool_calls=(
                [tool_calls_by_index[index] for index in sorted(tool_calls_by_index)]
                or None
            ),
        )

    async def check_health(self) -> bool:
        # Hive documents chat completions, not a health endpoint. Avoid spending a
        # paid completion just to answer a health probe.
        return bool(self.api_key)


def _retry_delay(
    retry_index: int,
    retry_after: str | None,
    policy: HiveRetryPolicy,
) -> float:
    server_delay = _retry_after_seconds(retry_after)
    if server_delay is not None:
        return min(server_delay, policy.retry_after_cap_seconds)
    ceiling = min(
        policy.backoff_cap_seconds,
        policy.backoff_base_seconds * (2**retry_index),
    )
    return random.uniform(0.0, ceiling)
