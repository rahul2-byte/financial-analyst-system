import json

import pytest

from app.models.request_models import ChatRequest, Message
from app.routes import chat


@pytest.mark.asyncio
async def test_chat_endpoint_streams_error_event_with_type_field(monkeypatch) -> None:
    async def _broken_execute_query(*_args, **_kwargs):
        raise RuntimeError("boom")
        yield  # pragma: no cover

    monkeypatch.setattr(chat.orchestrator, "execute_query", _broken_execute_query)

    request = ChatRequest(messages=[Message(role="user", content="hello")])
    response = await chat.chat_endpoint(request)

    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
        if len(chunks) >= 3:
            break

    error_chunk = chunks[1]
    payload = error_chunk.removeprefix("data: ").strip()
    event = json.loads(payload)

    assert event["type"] == "error"
    assert "boom" in event["message"]
