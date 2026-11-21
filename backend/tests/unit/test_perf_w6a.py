"""Reasoning control, HTTP hardening, pre-warm and per-call telemetry."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from app.config import settings
from app.config.reasoning import parse_reasoning
from app.core.resources import RuntimeResources
from app.models.request_models import Message
from app.services.jev_service import JevService
from app.services.openrouter_service import OpenRouterService
from scripts_loader import load_perf_report

_SSE = (
    b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
    b'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":7,'
    b'"completion_tokens_details":{"reasoning_tokens":3},'
    b'"prompt_tokens_details":{"cached_tokens":4}}}\n\n'
    b"data: [DONE]\n\n"
)


def _service(bodies: list[dict[str, Any]]) -> OpenRouterService:
    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, request=request, content=_SSE)

    return OpenRouterService(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        fallback_models=[],
    )


async def _send(service: OpenRouterService, **kwargs: Any) -> None:
    async for _ in service._stream_request(
        [Message(role="user", content="hi")], "m/x", **kwargs
    ):
        pass


def test_parse_reasoning_shapes() -> None:
    assert parse_reasoning("unset") is None
    assert parse_reasoning("off") == {"enabled": False}
    assert parse_reasoning("LOW") == {"effort": "low"}
    assert parse_reasoning("tokens:256") == {"max_tokens": 256}
    with pytest.raises(ValueError):
        parse_reasoning("fast")


def test_defaults() -> None:
    assert settings.FINAI_REASONING_SYNTHESIS == "unset"
    assert settings.FINAI_REASONING_TOOL_ROUNDS == "off"
    assert settings.FINAI_REASONING_REPAIR == "low"


@pytest.mark.asyncio
async def test_reasoning_field_per_purpose() -> None:
    bodies: list[dict[str, Any]] = []
    service = _service(bodies)
    for purpose in ("tool_selection", "repair", "synthesis", None):
        await _send(service, purpose=purpose) if purpose else await _send(service)
    assert bodies[0]["reasoning"] == {"enabled": False}
    assert bodies[1]["reasoning"] == {"effort": "low"}
    assert "reasoning" not in bodies[2]
    assert "reasoning" not in bodies[3]
    await service.aclose()


@pytest.mark.asyncio
async def test_synthesis_payload_unchanged_by_default() -> None:
    bodies: list[dict[str, Any]] = []
    service = _service(bodies)
    await _send(service, purpose="synthesis", max_tokens=99, temperature=0.1)
    await _send(service, max_tokens=99, temperature=0.1)
    assert bodies[0] == bodies[1]
    assert bodies[0] == {
        "model": "m/x",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "max_tokens": 99,
        "temperature": 0.1,
    }
    await service.aclose()


@pytest.mark.asyncio
async def test_synthesis_reasoning_only_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "FINAI_REASONING_SYNTHESIS", "medium")
    bodies: list[dict[str, Any]] = []
    service = _service(bodies)
    await _send(service, purpose="synthesis")
    assert bodies[0]["reasoning"] == {"effort": "medium"}
    await service.aclose()


@pytest.mark.asyncio
async def test_default_clients_have_limits_and_short_connect(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENROUTER_CONNECT_TIMEOUT", 3.0)
    service = OpenRouterService()
    pool = service._client._transport._pool  # type: ignore[attr-defined]
    assert pool._keepalive_expiry == 60.0
    assert pool._max_connections == settings.HTTP_POOL_MAX_CONNECTIONS
    assert service._client.timeout.connect == 3.0
    await service.aclose()
    jev = JevService(api_key="k", timeout_seconds=10.0)
    jpool = jev._client._transport._pool  # type: ignore[attr-defined]
    assert jpool._keepalive_expiry == 60.0
    assert jev._client.timeout.connect == 3.0
    assert jev._request_timeout().connect == 3.0
    assert jev._request_timeout().read == 10.0
    await jev._client.aclose()


@pytest.mark.asyncio
async def test_prewarm_failure_is_swallowed() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    service = OpenRouterService(
        client=httpx.AsyncClient(transport=httpx.MockTransport(boom))
    )
    assert await service.prewarm() is False
    await service.aclose()


@pytest.mark.asyncio
async def test_start_prewarm_never_blocks_or_raises() -> None:
    class Bad:
        async def prewarm(self) -> bool:
            raise RuntimeError("nope")

    resources = RuntimeResources(llm_service=Bad(), yf_fetcher=None)
    resources.start_prewarm()  # returns immediately
    assert resources._prewarm_task is not None
    await resources._prewarm_task  # exceptions are collected, not raised
    # outside a running loop it is a silent no-op
    RuntimeResources(llm_service=Bad(), yf_fetcher=None)


def test_start_prewarm_without_loop_is_noop() -> None:
    class Ok:
        async def prewarm(self) -> bool:
            return True

    resources = RuntimeResources(llm_service=Ok(), yf_fetcher=None)
    resources.start_prewarm()
    assert resources._prewarm_task is None


@pytest.mark.asyncio
async def test_prewarm_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "FINAI_HTTP_PREWARM", False)

    class Ok:
        async def prewarm(self) -> bool:
            return True

    resources = RuntimeResources(llm_service=Ok(), yf_fetcher=None)
    resources.start_prewarm()
    assert resources._prewarm_task is None


@pytest.mark.asyncio
async def test_call_metrics_persisted_and_reported(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "FINAI_CALL_METRICS", True)
    monkeypatch.setattr(settings, "FINAI_CALL_METRICS_DIR", str(tmp_path))
    bodies: list[dict[str, Any]] = []
    service = _service(bodies)
    await _send(service, purpose="repair", run_id="r1")
    await _send(service, purpose="synthesis", run_id="r1")
    lines = (tmp_path / "model-calls.jsonl").read_text().splitlines()
    first = json.loads(lines[0])
    assert first["purpose"] == "repair" and first["repair"] is True
    assert first["model"] == "m/x"
    assert first["prompt_tokens"] == 10
    assert first["completion_tokens"] == 7
    assert first["reasoning_tokens"] == 3
    assert first["cached_tokens"] == 4
    assert first["retries"] == 0
    assert first["total_ms"] >= 0 and first["ttft_ms"] is not None
    assert first["reasoning_param"] == {"effort": "low"}
    assert json.loads(lines[1])["repair"] is False

    report = load_perf_report()
    summary = report.summarize(report.load_records([tmp_path]))
    assert summary["repair"]["n"] == 1
    assert summary["synthesis"]["reasoning_tokens"]["median"] == 3.0
    assert "synthesis" in report.render(summary)
    await service.aclose()


@pytest.mark.asyncio
async def test_model_streaming_threads_purpose() -> None:
    from uuid import uuid4

    from app.core.agent_loop.model_streaming import ModelStreaming
    from app.events.models import EventFactory

    seen: list[str] = []

    class Client:
        def generate_stream(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
            seen.append(kwargs["purpose"])

            async def gen():  # type: ignore[no-untyped-def]
                if False:
                    yield {}

            return gen()

    tools = [{"type": "function", "function": {"name": "t"}}]

    async def run(messages: list[Message], structured: bool = True) -> None:
        streamer = ModelStreaming(
            Client(), "m", 100, lambda: tools, structured_output=structured
        )
        factory = EventFactory(conversation_id=uuid4(), run_id=uuid4())
        async for _ in streamer.stream(messages, factory, 1):
            pass

    user = Message(role="user", content="q")
    await run([user])
    await run([user, Message(role="tool", content="{}", tool_call_id="1")])
    await run([user], structured=False)
    await run(
        [
            user,
            Message(
                role="system", content="fix", prompt_key="publication.report_repair"
            ),
        ]
    )
    assert seen == ["tool_selection", "synthesis", "synthesis", "repair"]
