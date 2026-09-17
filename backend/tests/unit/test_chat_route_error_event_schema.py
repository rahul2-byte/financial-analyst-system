import json

import pytest
from app.models.request_models import ChatRequest, Message
from app.routes import chat


@pytest.mark.asyncio
async def test_chat_route_has_no_orchestrator_global(monkeypatch) -> None:
    assert not hasattr(chat, "orchestrator")


@pytest.mark.asyncio
async def test_chat_endpoint_streams_error_event_with_type_field(monkeypatch) -> None:
    async def _broken_run(*_args, **_kwargs):
        raise RuntimeError("boom")
        yield  # pragma: no cover

    class BrokenRuntime:
        def run(self, *_args, **_kwargs):
            return _broken_run()

    monkeypatch.setattr(chat, "_runtime", lambda _request: BrokenRuntime())

    request = ChatRequest(messages=[Message(role="user", content="hello")])
    response = await chat.chat_endpoint(request)

    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
        if len(chunks) >= 3:
            break

    error_chunk = chunks[1]
    payload = str(error_chunk).removeprefix("data: ").strip()
    event = json.loads(payload)

    assert event["type"] == "error"
    assert "boom" in event["message"]
