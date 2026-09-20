import asyncio
import json

import httpx
import pytest
from app.config import settings
from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpen
from app.models.request_models import Message
from app.observability.provider_archive import ProviderArchive
from app.services.hive_service import (
    HiveProviderError,
    HiveRetryPolicy,
    HiveService,
    _retry_delay,
    _retryable_status,
    merge_tool_call_deltas,
)


def test_hive_retries_transient_gateway_failures() -> None:
    assert _retryable_status(408)
    assert _retryable_status(429)
    assert _retryable_status(502)
    assert _retryable_status(504)
    assert not _retryable_status(400)
    assert not _retryable_status(501)


def test_hive_default_total_timeout_is_ten_minutes() -> None:
    assert settings.HIVE_TIMEOUT == 600.0
    assert settings.HIVE_READ_TIMEOUT == 60.0


@pytest.mark.asyncio
async def test_hive_request_budget_uses_configured_timeout(monkeypatch) -> None:
    monkeypatch.setattr(settings, "HIVE_TIMEOUT", 123.0)

    service = HiveService(
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200))
        )
    )

    assert service.retry_policy.total_budget_seconds == 123.0
    await service.aclose()


@pytest.mark.asyncio
async def test_hive_reuses_injected_client_and_retries_504_before_streaming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(504, request=request, text="gateway timeout")
        return httpx.Response(
            200,
            request=request,
            content=(
                b'data: {"choices":[{"delta":{"content":"ready"}}]}\n\ndata: [DONE]\n\n'
            ),
        )

    monkeypatch.setattr(settings, "HIVE_API_KEY", "test-key")
    monkeypatch.setattr(settings, "HIVE_MAX_RETRIES", 1)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = HiveService(client=client)

    events = [
        event
        async for event in service._stream_request(
            [Message(role="user", content="hello")],
            settings.HIVE_MODEL,
        )
    ]

    assert attempts == 2
    assert [event["event"] for event in events] == [
        "provider_attempt_started",
        "provider_retrying",
        "provider_attempt_started",
        "provider_stream_started",
        "token",
        "done",
        "provider_completed",
    ]
    await service.aclose()
    assert client.is_closed


@pytest.mark.asyncio
async def test_hive_reports_started_stream_timeout_before_budget_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StalledStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield (
                b'data: {"choices":[{"delta":{"reasoning_content":"thinking"}}]}\n\n'
            )
            await asyncio.sleep(0.2)

        async def aclose(self) -> None:
            return None

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, stream=StalledStream())

    monkeypatch.setattr(settings, "HIVE_API_KEY", "test-key")
    service = HiveService(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        retry_policy=HiveRetryPolicy(
            max_retries=2,
            total_budget_seconds=0.05,
            backoff_base_seconds=0.01,
            backoff_cap_seconds=0.01,
            read_timeout_seconds=1.0,
        ),
    )

    events = []
    with pytest.raises(HiveProviderError, match="TimeoutError|budget exhausted"):
        async for event in service._stream_request(
            [Message(role="user", content="hello")], settings.HIVE_MODEL
        ):
            events.append(event)

    failures = [event for event in events if event["event"] == "provider_failed"]
    assert len(failures) == 1
    assert failures[0]["data"]["timeout"] is True
    assert failures[0]["data"]["partial_output"] is True
    assert not any(event["event"] == "provider_retrying" for event in events)
    await service.aclose()


@pytest.mark.asyncio
async def test_hive_archives_completed_raw_model_stream(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "HIVE_API_KEY", "test-key")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                content=b'data: {"choices":[{"delta":{"content":"ready"}}]}\n\ndata: [DONE]\n\n',
            )
        )
    )
    service = HiveService(client=client, provider_archive=ProviderArchive(tmp_path))

    events = [
        event
        async for event in service._stream_request(
            [Message(role="user", content="hello")],
            settings.HIVE_MODEL,
            run_id="run-123",
        )
    ]

    snapshot_hash = service.last_telemetry["snapshot_hash"]
    snapshot = service.provider_archive.load(snapshot_hash)
    assert snapshot.operation == "model_stream"
    assert any(event["event"] == "token" for event in snapshot.payload)
    assert events[-1]["event"] == "provider_completed"
    assert events[-1]["data"]["usage"] is None
    assert service.last_telemetry["run_id"] == "run-123"
    await service.aclose()


def test_hive_sse_parser_extracts_text_tool_calls_and_usage() -> None:
    parser = HiveService.parse_sse_line

    token = parser("data: " + json.dumps({"choices": [{"delta": {"content": "Hi"}}]}))
    usage = parser(
        "data: "
        + json.dumps(
            {"choices": [], "usage": {"prompt_tokens": 4, "completion_tokens": 2}}
        )
    )
    done = parser("data: [DONE]")

    assert token == {"event": "token", "data": "Hi"}
    assert usage == {
        "event": "usage",
        "data": {"prompt_tokens": 4, "completion_tokens": 2},
    }
    assert done == {"event": "done", "data": "[DONE]"}


def test_hive_sse_parser_rejects_malformed_json() -> None:
    with pytest.raises(HiveProviderError, match="malformed SSE"):
        HiveService.parse_sse_line("data: {broken")


def test_retry_delay_honors_retry_after_and_jitters_without_server_hint() -> None:
    policy = HiveRetryPolicy(2, 100.0, 0.5, 4.0)

    assert _retry_delay(0, "12", policy) == 10.0
    assert 0.0 <= _retry_delay(1, None, policy) <= 1.0


@pytest.mark.asyncio
async def test_hive_circuit_breaker_fails_fast_after_exhausted_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request, text="unavailable")

    monkeypatch.setattr(settings, "HIVE_API_KEY", "test-key")
    breaker = CircuitBreaker("test-hive", failure_threshold=2, recovery_timeout=60)
    service = HiveService(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        retry_policy=HiveRetryPolicy(0, 10.0, 0.5, 1.0),
        circuit_breaker=breaker,
    )

    for _ in range(2):
        with pytest.raises(HiveProviderError):
            [
                event
                async for event in service._stream_request(
                    [Message(role="user", content="hello")], settings.HIVE_MODEL
                )
            ]
    with pytest.raises(CircuitBreakerOpen):
        [
            event
            async for event in service._stream_request(
                [Message(role="user", content="hello")], settings.HIVE_MODEL
            )
        ]
    await service.aclose()


def test_hive_sse_parser_preserves_content_and_usage_in_one_frame() -> None:
    event = HiveService.parse_sse_line(
        "data: "
        + json.dumps(
            {
                "choices": [{"delta": {"content": "Hi"}}],
                "usage": {"prompt_tokens": 4},
            }
        )
    )

    assert event == {
        "event": "token",
        "data": "Hi",
        "usage": {"prompt_tokens": 4},
    }


def test_tool_call_fragments_are_assembled_by_index_and_id() -> None:
    calls: dict[int, dict[str, object]] = {}

    merge_tool_call_deltas(
        calls,
        [
            {
                "index": 0,
                "id": "call_1",
                "type": "function",
                "function": {"name": "search_web", "arguments": '{"q":"A'},
            }
        ],
    )
    merge_tool_call_deltas(
        calls,
        [
            {
                "index": 0,
                "function": {"arguments": 'APL"}'},
            }
        ],
    )

    assert calls == {
        0: {
            "index": 0,
            "id": "call_1",
            "type": "function",
            "function": {"name": "search_web", "arguments": '{"q":"AAPL"}'},
        }
    }
