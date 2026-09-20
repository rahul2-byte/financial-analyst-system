from __future__ import annotations

import asyncio
import json

import httpx
from app.models.request_models import Message
from app.services.anthropic_service import AnthropicService


def test_anthropic_stream_normalizes_text_events() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "test-key"
        assert request.url.path == "/v1/messages"
        body = json.dumps({"type": "content_block_delta", "delta": {"text": "hello"}})
        done = json.dumps({"type": "message_stop"})
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=f"data: {body}\n\ndata: {done}\n\n".encode(),
        )

    service = AnthropicService(
        api_key="test-key",
        model="claude-test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    async def collect():
        return [
            event
            async for event in service.generate_stream(
                [Message(role="user", content="hello")], "reasoning"
            )
        ]

    events = asyncio.run(collect())

    assert events[0] == {"event": "token", "data": "hello"}
    assert events[-1] == {"event": "done", "data": "[DONE]"}
