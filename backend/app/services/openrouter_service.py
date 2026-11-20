from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from app.config import settings
from app.core.circuit_breaker import CircuitBreaker
from app.core.model_call_trace import (
    ModelCallTrace,
    call_started,
    capture_stream,
    safe_endpoint,
)
from app.core.model_stream import get_public_token_sink
from app.core.observability import observe
from app.models.request_models import Message
from app.observability.provider_archive import ProviderArchive, ProviderSnapshot
from app.observability.provider_metrics import ProviderMetrics
from app.observability.tracing import (
    add_current_span_event,
    set_current_span_attributes,
    trace_content,
)
from app.services.llm_interface import LLMServiceInterface

logger = logging.getLogger(__name__)


class OpenRouterProviderError(RuntimeError):
    """A provider or stream protocol failure from OpenRouter."""


def _retryable_status(status_code: int) -> bool:
    return status_code in {408, 429, 500, 502, 503, 504}


def failure_reason(status_code: int | None = None, *, timeout: bool = False) -> str:
    """Map an HTTP status or timeout to the runtime's provider reason classes."""
    if timeout or status_code == 408:
        return "timeout"
    if status_code == 402:
        return "quota"
    if status_code in {401, 403}:
        return "auth"
    if status_code == 429:
        return "rate_limit"
    if status_code is not None and status_code >= 500:
        return "server_error"
    return "error"


_MISSING_KEY_MESSAGE = (
    "OPENROUTER_API_KEY is not set. Get a key at https://openrouter.ai/keys "
    "and add it to .env."
)


@dataclass(frozen=True)
class OpenRouterRetryPolicy:
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


class OpenRouterService(LLMServiceInterface):
    """OpenAI-compatible streaming client for OpenRouter chat completions."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        provider_name: str = "openrouter",
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
        fallback_models: list[str] | None = None,
        retry_policy: OpenRouterRetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        provider_archive: ProviderArchive | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.base_url = str(base_url or settings.OPENROUTER_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.OPENROUTER_API_KEY
        self.default_model = str(default_model or settings.OPENROUTER_MODEL)
        self.fallback_models = list(
            settings.openrouter_fallback_models
            if fallback_models is None
            else fallback_models
        )
        self.last_telemetry: dict[str, Any] = {}
        self.provider_archive = provider_archive
        self.metrics = ProviderMetrics()
        self.retry_policy = retry_policy or OpenRouterRetryPolicy(
            max_retries=settings.OPENROUTER_MAX_RETRIES,
            total_budget_seconds=settings.OPENROUTER_TIMEOUT,
            backoff_base_seconds=settings.OPENROUTER_BACKOFF_BASE,
            backoff_cap_seconds=settings.OPENROUTER_BACKOFF_CAP,
        )
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=settings.OPENROUTER_CONNECT_TIMEOUT,
                pool=settings.OPENROUTER_POOL_TIMEOUT,
                write=settings.OPENROUTER_WRITE_TIMEOUT,
                read=settings.OPENROUTER_READ_TIMEOUT,
            ),
            limits=httpx.Limits(
                max_connections=settings.HTTP_POOL_MAX_CONNECTIONS,
                max_keepalive_connections=settings.HTTP_POOL_MAX_KEEPALIVE_CONNECTIONS,
            ),
        )
        self._circuit = circuit_breaker or CircuitBreaker(
            self.provider_name,
            failure_threshold=settings.OPENROUTER_CIRCUIT_FAILURE_THRESHOLD,
            recovery_timeout=settings.OPENROUTER_CIRCUIT_RECOVERY_TIMEOUT,
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
            raise OpenRouterProviderError(f"malformed SSE payload: {exc}") from exc
        if not isinstance(chunk, dict):
            raise OpenRouterProviderError("malformed SSE payload: expected object")
        if isinstance(chunk.get("error"), dict):
            err = chunk["error"]
            raise OpenRouterProviderError(
                f"OpenRouter stream error {err.get('code', '')}: "
                f"{str(err.get('message', ''))[:300]}"
            )
        usage = chunk.get("usage")
        choices = chunk.get("choices", [])
        if isinstance(usage, dict) and not choices:
            return {"event": "usage", "data": usage}
        delta = (
            choices[0].get("delta", {})
            if choices and isinstance(choices[0], dict)
            else {}
        )
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

    @observe("llm.openrouter", as_type="llm", provider="openrouter")
    async def _stream_request(
        self, messages: list[Message], model: str, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        if not self.api_key:
            raise OpenRouterProviderError(_MISSING_KEY_MESSAGE)
        if not self._circuit.try_acquire():
            from app.core.circuit_breaker import CircuitBreakerOpen

            raise CircuitBreakerOpen(f"Circuit '{self.provider_name}' is open")
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": self._model(model),
            "messages": [message.model_dump(exclude_none=True) for message in messages],
            "stream": True,
            "max_tokens": kwargs.get(
                "max_tokens", settings.OPENROUTER_MAX_OUTPUT_TOKENS
            ),
            "temperature": kwargs.get("temperature", 0.7),
        }
        # OpenRouter performs model failover natively from the ``models`` array.
        if self.fallback_models:
            payload["models"] = [
                payload["model"],
                *(m for m in self.fallback_models if m != payload["model"]),
            ]
        prompt_content, prompt_truncated, prompt_size = trace_content(
            payload["messages"]
        )
        set_current_span_attributes(
            {
                "llm.invocation_parameters": json.dumps(
                    {
                        "temperature": payload["temperature"],
                        "max_tokens": payload["max_tokens"],
                    },
                    sort_keys=True,
                ),
                "llm.input.messages": prompt_content,
                "llm.input.truncated": prompt_truncated,
                "llm.input.bytes": prompt_size,
            }
        )
        run_id = kwargs.get("run_id")
        if kwargs.get("tools"):
            payload["tools"] = kwargs["tools"]
            tools_content, tools_truncated, tools_size = trace_content(payload["tools"])
            set_current_span_attributes(
                {
                    "llm.tool_definitions": tools_content,
                    "llm.tools.truncated": tools_truncated,
                    "llm.tools.bytes": tools_size,
                }
            )
        retries = 0
        request_deadline = started + float(
            kwargs.get("timeout_seconds") or self.retry_policy.total_budget_seconds
        )
        streamed_token_count = 0
        reasoning_chunk_count = 0
        reasoning_chars = 0
        public_token_chars = 0
        public_text: list[str] = []
        emitted_tool_call = False
        finish_reason: str | None = None
        stream_started = False
        raw_events: list[dict[str, Any]] = []
        while True:
            first_token_at: float | None = None
            usage: dict[str, Any] | None = None
            attempt = retries + 1
            attempt_event = {
                "event": "provider_attempt_started",
                "data": {"attempt": attempt, "provider": self.provider_name},
            }
            add_current_span_event("llm.attempt", {"retry.attempt": attempt})
            set_current_span_attributes(
                {
                    "llm.provider": self.provider_name,
                    "llm.model_name": self._model(model),
                }
            )
            yield attempt_event
            try:
                remaining = request_deadline - time.perf_counter()
                if remaining <= 0:
                    raise OpenRouterProviderError("OpenRouter request budget exhausted")
                # The client's read timeout is only a per-read limit. The
                # request budget must also cap the whole attempt, otherwise a
                # stalled SSE stream can run past the configured deadline.
                async with asyncio.timeout(remaining):
                    trace = kwargs.get("_model_call_trace")
                    if isinstance(trace, ModelCallTrace):
                        trace.write(
                            "request.attempt",
                            {
                                "attempt": attempt,
                                "provider": self.provider_name,
                                "endpoint": safe_endpoint(
                                    f"{self.base_url}/chat/completions"
                                ),
                                "request_body": payload,
                            },
                        )
                    async with self._client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "X-Title": "FIN-AI",
                            **(
                                {"HTTP-Referer": settings.OPENROUTER_APP_URL}
                                if settings.OPENROUTER_APP_URL
                                else {}
                            ),
                            "Content-Type": "application/json",
                            "Accept": "text/event-stream",
                        },
                    ) as response:
                        if response.status_code != 200:
                            body = (await response.aread()).decode(errors="replace")
                            trace = kwargs.get("_model_call_trace")
                            if isinstance(trace, ModelCallTrace):
                                trace.write(
                                    "response.http_error",
                                    {
                                        "attempt": attempt,
                                        "status_code": response.status_code,
                                        "body": body,
                                    },
                                )
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
                                    raise OpenRouterProviderError(
                                        "OpenRouter request budget exhausted during retry"
                                    )
                                retries += 1
                                retry_event = {
                                    "event": "provider_retrying",
                                    "data": {
                                        "attempt": attempt,
                                        "status_code": response.status_code,
                                        "delay_ms": round(delay * 1000, 2),
                                        "reason": f"HTTP {response.status_code}",
                                    },
                                }
                                raw_events.append(retry_event)
                                add_current_span_event(
                                    "retry.scheduled",
                                    {
                                        "retry.attempt": attempt,
                                        "retry.reason": f"HTTP {response.status_code}",
                                        "retry.backoff_ms": round(delay * 1000, 2),
                                    },
                                )
                                yield retry_event
                                await asyncio.sleep(delay)
                                continue
                            yield {
                                "event": "provider_failed",
                                "data": {
                                    "attempts": attempt,
                                    "phase": "http",
                                    "status_code": response.status_code,
                                    "message": f"OpenRouter HTTP {response.status_code}",
                                    "provider": self.provider_name,
                                    "reason": failure_reason(response.status_code),
                                    "model_id": self._model(model),
                                    "timeout": response.status_code == 408,
                                    "partial_output": False,
                                    "usage": usage,
                                },
                            }
                            raise OpenRouterProviderError(
                                f"OpenRouter HTTP {response.status_code}: {body[:500]}"
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
                                stream_started = True
                                stream_event = {
                                    "event": "provider_stream_started",
                                    "data": {
                                        "attempt": attempt,
                                        "first_byte_ms": round(
                                            (time.perf_counter() - started) * 1000, 2
                                        ),
                                    },
                                }
                                raw_events.append(stream_event)
                                yield stream_event
                            parsed = self.parse_sse_line(line)
                            if not parsed:
                                continue
                            if parsed["event"] == "usage":
                                usage = parsed["data"]
                                set_current_span_attributes(
                                    {
                                        "llm.token_count.prompt": usage.get(
                                            "prompt_tokens", 0
                                        ),
                                        "llm.token_count.completion": usage.get(
                                            "completion_tokens", 0
                                        ),
                                        "llm.token_count.total": usage.get(
                                            "total_tokens", 0
                                        ),
                                    }
                                )
                                raw_events.append(parsed)
                                yield parsed
                            elif parsed["event"] == "token":
                                first_token_at = first_token_at or time.perf_counter()
                                streamed_token_count += 1
                                public_token_chars += len(str(parsed["data"]))
                                public_text.append(str(parsed["data"]))
                                logger.debug(
                                    "OpenRouter SSE token chunk received",
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
                                raw_events.append(parsed)
                                yield parsed
                            elif parsed["event"] == "done":
                                saw_done = True
                                raw_events.append(parsed)
                                yield parsed
                                break
                            elif parsed["event"] == "chunk":
                                if isinstance(parsed.get("usage"), dict):
                                    usage = parsed["usage"]
                                choices = parsed["data"].get("choices", [])
                                delta = choices[0].get("delta", {}) if choices else {}
                                if choices and choices[0].get("finish_reason"):
                                    finish_reason = str(choices[0]["finish_reason"])
                                if isinstance(delta, dict) and delta.get(
                                    "reasoning_content"
                                ):
                                    reasoning_chunk_count += 1
                                    reasoning_chars += len(
                                        str(delta["reasoning_content"])
                                    )
                                if isinstance(delta, dict) and delta.get("tool_calls"):
                                    emitted_tool_call = True
                                raw_events.append(parsed)
                                yield parsed
                        if not saw_done:
                            raise OpenRouterProviderError(
                                "incomplete OpenRouter SSE stream"
                            )
                self.last_telemetry = {
                    "model_id": self._model(model),
                    "run_id": run_id,
                    "request_latency_ms": round(
                        (time.perf_counter() - started) * 1000, 2
                    ),
                    "first_token_latency_ms": round(
                        (first_token_at - started) * 1000, 2
                    )
                    if first_token_at
                    else None,
                    "retry_count": retries,
                    "provider_status": "completed",
                    "streamed_token_count": streamed_token_count,
                    "public_token_chars": public_token_chars,
                    "reasoning_chunk_count": reasoning_chunk_count,
                    "reasoning_chars": reasoning_chars,
                    "usage": usage,
                }
                if finish_reason:
                    set_current_span_attributes({"llm.finish_reason": finish_reason})
                output_content, output_truncated, output_size = trace_content(
                    "".join(public_text)
                )
                set_current_span_attributes(
                    {
                        "llm.output": output_content,
                        "llm.output.truncated": output_truncated,
                        "llm.output.bytes": output_size,
                    }
                )
                if self.provider_archive is not None:
                    snapshot = self.provider_archive.store(
                        ProviderSnapshot(
                            provider=self.provider_name,
                            operation="model_stream",
                            payload=raw_events,
                            fetched_at=datetime.now(UTC),
                        )
                    )
                    self.last_telemetry["snapshot_hash"] = snapshot.content_hash
                self.metrics.record(
                    status="completed",
                    latency_ms=self.last_telemetry["request_latency_ms"],
                    timeout=False,
                    partial=bool(streamed_token_count and not saw_done),
                )
                self._circuit.record_success()
                yield {
                    "event": "provider_completed",
                    "data": {
                        "model_id": self.last_telemetry["model_id"],
                        "attempts": attempt,
                        "duration_ms": self.last_telemetry["request_latency_ms"],
                        "first_token_ms": self.last_telemetry["first_token_latency_ms"],
                        "usage": usage,
                    },
                }
                return
            except (TimeoutError, httpx.TimeoutException, httpx.TransportError) as exc:
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                self.last_telemetry = {
                    "model_id": self._model(model),
                    "run_id": run_id,
                    "request_latency_ms": latency_ms,
                    "provider_status": "failed",
                    "timeout": isinstance(exc, (TimeoutError, httpx.TimeoutException)),
                    "partial_output": bool(streamed_token_count or emitted_tool_call),
                    "usage": usage,
                }
                self.metrics.record(
                    status="failed",
                    latency_ms=latency_ms,
                    timeout=self.last_telemetry["timeout"],
                    partial=self.last_telemetry["partial_output"],
                )
                partial_output = (
                    stream_started or streamed_token_count > 0 or emitted_tool_call
                )
                if partial_output:
                    yield {
                        "event": "provider_failed",
                        "data": {
                            "attempts": attempt,
                            "phase": "transport",
                            "message": type(exc).__name__,
                            "provider": self.provider_name,
                            "reason": failure_reason(
                                timeout=self.last_telemetry["timeout"]
                            ),
                            "model_id": self.last_telemetry["model_id"],
                            "duration_ms": latency_ms,
                            "timeout": self.last_telemetry["timeout"],
                            "partial_output": partial_output,
                            "usage": usage,
                        },
                    }
                    self._circuit.record_failure()
                    raise OpenRouterProviderError(
                        f"OpenRouter transport failed after the response had started: "
                        f"{type(exc).__name__}"
                    ) from exc
                if retries < self.retry_policy.max_retries:
                    delay = _retry_delay(retries, None, self.retry_policy)
                    if time.perf_counter() + delay >= request_deadline:
                        yield {
                            "event": "provider_failed",
                            "data": {
                                "attempts": attempt,
                                "phase": "transport",
                                "message": type(exc).__name__,
                                "provider": self.provider_name,
                                "reason": failure_reason(
                                    timeout=self.last_telemetry["timeout"]
                                ),
                                "model_id": self.last_telemetry["model_id"],
                                "duration_ms": latency_ms,
                                "timeout": self.last_telemetry["timeout"],
                                "partial_output": partial_output,
                                "usage": usage,
                            },
                        }
                        self._circuit.record_failure()
                        raise OpenRouterProviderError(
                            f"OpenRouter transport failure: {type(exc).__name__}"
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
                        "provider": self.provider_name,
                        "reason": failure_reason(
                            timeout=self.last_telemetry["timeout"]
                        ),
                        "model_id": self.last_telemetry["model_id"],
                        "duration_ms": latency_ms,
                        "timeout": self.last_telemetry["timeout"],
                        "partial_output": self.last_telemetry["partial_output"],
                        "usage": usage,
                    },
                }
                self._circuit.record_failure()
                raise OpenRouterProviderError(
                    f"OpenRouter transport failure: {exc}"
                ) from exc
            except OpenRouterProviderError as exc:
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                self.last_telemetry = {
                    "model_id": self._model(model),
                    "run_id": run_id,
                    "request_latency_ms": latency_ms,
                    "provider_status": "failed",
                    "timeout": "timeout" in str(exc).lower(),
                    "partial_output": bool(streamed_token_count or emitted_tool_call),
                    "usage": usage,
                }
                self.metrics.record(
                    status="failed",
                    latency_ms=latency_ms,
                    timeout=self.last_telemetry["timeout"],
                    partial=self.last_telemetry["partial_output"],
                )
                self._circuit.record_failure()
                raise

    def generate_stream(
        self, messages: list[Message], model: str, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        async def generator() -> AsyncGenerator[dict[str, Any], None]:
            trace = kwargs.get("_model_call_trace")
            owns_trace = not isinstance(trace, ModelCallTrace)
            if owns_trace:
                trace = ModelCallTrace.create(
                    provider=self.provider_name,
                    model=self._model(model),
                    run_id=str(kwargs["run_id"]) if kwargs.get("run_id") else None,
                    conversation_id=(
                        str(kwargs["conversation_id"])
                        if kwargs.get("conversation_id")
                        else None
                    ),
                    call_id=str(kwargs.get("model_call_id") or uuid4()),
                )
                call_started(
                    trace,
                    messages=messages,
                    tools=kwargs.get("tools"),
                    parameters={
                        key: kwargs.get(key)
                        for key in ("max_tokens", "temperature", "timeout_seconds")
                        if kwargs.get(key) is not None
                    },
                )
            traced_kwargs = {**kwargs, "_model_call_trace": trace}
            source = self._stream_request(messages, model, **traced_kwargs)
            if owns_trace and isinstance(trace, ModelCallTrace):
                source = capture_stream(trace, source)
            async for event in source:
                public = {"event": event["event"], "data": event["data"]}
                if "chunk" in event:
                    public["chunk"] = event["chunk"]
                if "usage" in event:
                    public["usage"] = event["usage"]
                yield public

        return generator()

    async def generate(self, messages: list[Message], model: str, **kwargs: Any) -> str:
        parts: list[str] = []
        async for event in self.generate_stream(messages, model, **kwargs):
            if event["event"] == "token":
                parts.append(str(event["data"]))
        return "".join(parts)

    async def generate_message(
        self, messages: list[Message], model: str, **kwargs: Any
    ) -> Message:
        parts: list[str] = []
        tool_calls_by_index: dict[int, dict[str, Any]] = {}
        async for event in self.generate_stream(messages, model, **kwargs):
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
        # OpenRouter documents chat completions, not a health endpoint. Avoid spending a
        # paid completion just to answer a health probe.
        return bool(self.api_key)


def _retry_delay(
    retry_index: int,
    retry_after: str | None,
    policy: OpenRouterRetryPolicy,
) -> float:
    server_delay = _retry_after_seconds(retry_after)
    if server_delay is not None:
        return min(server_delay, policy.retry_after_cap_seconds)
    ceiling = min(
        policy.backoff_cap_seconds,
        policy.backoff_base_seconds * (2**retry_index),
    )
    return random.uniform(0.0, ceiling)
