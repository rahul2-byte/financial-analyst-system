import json

import pytest
from app.models.request_models import ChatRequest, Message
from app.routes import chat
from fastapi import HTTPException


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
    monkeypatch.setattr(chat.settings, "HTTP_API_TOKEN", "test-token")
    monkeypatch.setattr(chat.settings, "HTTP_API_OWNER", "test-owner")
    response = await chat.chat_endpoint(request, authorization="Bearer test-token")

    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
        if len(chunks) >= 3:
            break

    error_chunk = chunks[1]
    payload = str(error_chunk).removeprefix("data: ").strip()
    event = json.loads(payload)

    assert event["type"] == "error"
    assert event["message"].startswith("The research request failed. Reference: ")
    assert "boom" not in event["message"]


def test_http_authentication_derives_an_owner_scoped_conversation_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat.settings, "HTTP_API_TOKEN", "test-token")
    monkeypatch.setattr(chat.settings, "HTTP_API_OWNER", "test-owner")

    owner = chat._authenticated_owner("Bearer test-token")

    assert owner == "test-owner"
    assert chat._conversation_id(owner, "shared") != chat._conversation_id(
        "other", "shared"
    )


def test_http_authentication_rejects_missing_or_wrong_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat.settings, "HTTP_API_TOKEN", "test-token")

    with pytest.raises(HTTPException) as missing:
        chat._authenticated_owner(None)
    with pytest.raises(HTTPException) as wrong:
        chat._authenticated_owner("Bearer wrong")

    assert missing.value.status_code == 401
    assert wrong.value.status_code == 401
