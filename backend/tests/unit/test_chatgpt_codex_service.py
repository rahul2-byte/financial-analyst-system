import asyncio
import json
import urllib.parse

import httpx
import pytest
from app.models.request_models import Message
from app.services.chatgpt_codex_service import (
    ChatGPTCodexError,
    ChatGPTCodexService,
    CodexCredentialStore,
    OAuthStateError,
    _response_tool,
    _responses_input,
)


@pytest.mark.asyncio
async def test_codex_generate_has_total_deadline_for_heartbeating_stream(
    tmp_path, monkeypatch
) -> None:
    service = ChatGPTCodexService(
        client=httpx.AsyncClient(),
        credential_store=CodexCredentialStore(tmp_path / "credentials.json"),
        timeout_seconds=0.01,
    )

    async def heartbeat(messages, model, **kwargs):
        while True:
            await asyncio.sleep(0)
            yield {"event": "provider_stream_started", "data": {}}

    monkeypatch.setattr(service, "generate_stream", heartbeat)

    with pytest.raises(ChatGPTCodexError, match="total timeout"):
        await service.generate([Message(role="user", content="hello")], "gpt-test")

    await service.aclose()


def test_authorization_url_contains_pkce_and_state() -> None:
    service = ChatGPTCodexService(client=httpx.AsyncClient())

    url = service.authorization_url()

    assert "https://auth.openai.com/oauth/authorize" in url
    assert "code_challenge=" in url
    assert "state=" in url
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert query["id_token_add_organizations"] == ["true"]
    assert query["codex_cli_simplified_flow"] == ["true"]
    assert query["originator"] == ["opencode"]
    assert query["redirect_uri"] == ["http://localhost:1455/auth/callback"]
    assert service.pending_state
    assert service.pending_verifier


def test_callback_rejects_wrong_state() -> None:
    service = ChatGPTCodexService(client=httpx.AsyncClient())
    service.authorization_url()

    with pytest.raises(OAuthStateError):
        service.validate_callback("code", "wrong-state")


def test_credential_store_writes_owner_only_json(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    store = CodexCredentialStore(path)

    store.save({"access_token": "secret", "expires_at": 123})

    assert json.loads(path.read_text())["access_token"] == "secret"
    assert path.stat().st_mode & 0o077 == 0


def test_response_tools_use_provider_safe_names() -> None:
    tool = _response_tool(
        {
            "type": "function",
            "function": {"name": "data:fetch_stock_data", "parameters": {}},
        }
    )

    assert tool["name"] == "data__fetch_stock_data"


def test_responses_input_preserves_paired_function_calls_and_drops_orphans() -> None:
    call = {
        "id": "call-valid",
        "type": "function",
        "function": {
            "name": "data:fetch_stock_data",
            "arguments": '{"ticker":"TCS.NS"}',
        },
    }
    input_items = _responses_input(
        [
            Message(role="user", content="Get TCS data"),
            Message(role="assistant", content="", tool_calls=[call]),
            Message(role="tool", content='{"close": 100}', tool_call_id="call-valid"),
            Message(role="tool", content="stale", tool_call_id="call-orphan"),
        ]
    )

    assert {
        "type": "function_call",
        "call_id": "call-valid",
        "name": "data__fetch_stock_data",
        "arguments": '{"ticker":"TCS.NS"}',
    } in input_items
    assert {
        "type": "function_call_output",
        "call_id": "call-valid",
        "output": '{"close": 100}',
    } in input_items
    assert not any(item.get("call_id") == "call-orphan" for item in input_items)


@pytest.mark.asyncio
async def test_codex_stream_translates_text_and_completion(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/backend-api/codex/responses"
        assert request.headers["Authorization"] == "Bearer access"
        payload = json.loads(request.content)
        assert "max_output_tokens" not in payload
        assert "temperature" not in payload
        return httpx.Response(
            200,
            request=request,
            content=(
                b"event: response.output_text.delta\n"
                b'data: {"delta":"Hello"}\n\n'
                b"event: response.completed\n"
                b'data: {"response":{"usage":{"input_tokens":2,"output_tokens":1}}}\n\n'
            ),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = ChatGPTCodexService(
        client=client,
        credential_store=CodexCredentialStore(tmp_path / "credentials.json"),
    )
    service.credential_store.save(
        {"access_token": "access", "expires_at": 9_999_999_999}
    )

    events = [
        event
        async for event in service.generate_stream(
            [Message(role="user", content="hello")], "gpt-test"
        )
    ]

    assert [event["event"] for event in events] == [
        "provider_attempt_started",
        "provider_stream_started",
        "token",
        "provider_completed",
    ]
    assert events[2]["data"] == "Hello"
    assert events[1]["data"]["provider"] == "chatgpt_codex"
    assert events[3]["data"]["provider"] == "chatgpt_codex"
    assert events[3]["data"]["duration_ms"] > 0
    assert isinstance(events[3]["data"]["first_token_ms"], float)
    await service.aclose()


@pytest.mark.asyncio
async def test_codex_trace_records_sent_body_and_assembled_response(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("FINAI_MODEL_TRACE", "full")
    monkeypatch.setenv("FINAI_MODEL_TRACE_DIR", str(tmp_path / "traces"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            content=(
                b"event: response.output_text.delta\n"
                b'data: {"delta":"Answer"}\n\n'
                b"event: response.completed\n"
                b'data: {"response":{"usage":{"input_tokens":3,"output_tokens":1}}}\n\n'
            ),
        )

    service = ChatGPTCodexService(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        credential_store=CodexCredentialStore(tmp_path / "credentials.json"),
    )
    service.credential_store.save(
        {"access_token": "never-write-this", "expires_at": 9_999_999_999}
    )

    events = [
        event
        async for event in service.generate_stream(
            [Message(role="user", content="exact question")], "gpt-test", run_id="run-7"
        )
    ]

    trace_path = next((tmp_path / "traces").glob("**/*.jsonl"))
    records = [json.loads(line) for line in trace_path.read_text().splitlines()]
    request_record = next(
        record for record in records if record["event"] == "request.attempt"
    )
    response_record = next(
        record for record in records if record["event"] == "call.completed"
    )
    assert (
        request_record["payload"]["request_body"]["input"][0]["content"]
        == "exact question"
    )
    assert "never-write-this" not in trace_path.read_text()
    assert response_record["payload"]["text"] == "Answer"
    assert response_record["payload"]["chunk_timings"]
    assert response_record["run_id"] == "run-7"
    assert events[-1]["event"] == "provider_completed"
    await service.aclose()


@pytest.mark.asyncio
async def test_codex_trace_assembles_tool_call_arguments(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FINAI_MODEL_TRACE", "full")
    monkeypatch.setenv("FINAI_MODEL_TRACE_DIR", str(tmp_path / "traces"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            content=(
                b"event: response.output_item.done\n"
                b'data: {"item":{"type":"function_call","call_id":"c1",'
                b'"output_index":0,"name":"data__fetch_stock_data",'
                b'"arguments":"{\\"ticker\\":\\"TCS.NS\\"}"}}\n\n'
                b"event: response.completed\n"
                b'data: {"response":{}}\n\n'
            ),
        )

    service = ChatGPTCodexService(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        credential_store=CodexCredentialStore(tmp_path / "credentials.json"),
    )
    service.credential_store.save(
        {"access_token": "access", "expires_at": 9_999_999_999}
    )
    [
        event
        async for event in service.generate_stream([], "gpt-test", run_id="run-tool")
    ]

    trace_path = next((tmp_path / "traces").glob("**/*.jsonl"))
    records = [json.loads(line) for line in trace_path.read_text().splitlines()]
    completed = next(
        record for record in records if record["event"] == "call.completed"
    )
    assert completed["payload"]["tool_calls"][0]["function"] == {
        "name": "data:fetch_stock_data",
        "arguments": '{"ticker":"TCS.NS"}',
    }
    assert completed["payload"]["chunk_timings"]
    await service.aclose()


@pytest.mark.asyncio
async def test_codex_to_hive_fallback_keeps_one_correlated_trace(
    tmp_path, monkeypatch
) -> None:
    from app.config import settings
    from app.services.hive_service import HiveService

    monkeypatch.setenv("FINAI_MODEL_TRACE", "full")
    monkeypatch.setenv("FINAI_MODEL_TRACE_DIR", str(tmp_path / "traces"))
    monkeypatch.setattr(settings, "HIVE_API_KEY", "secret-hive-key")
    hive = HiveService(
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    request=request,
                    content=b'data: {"choices":[{"delta":{"content":"fallback answer"}}]}\n\ndata: [DONE]\n\n',
                )
            )
        )
    )
    service = ChatGPTCodexService(
        client=httpx.AsyncClient(),
        fallback=hive,
        credential_store=CodexCredentialStore(tmp_path / "missing-credentials.json"),
    )

    events = [
        event
        async for event in service.generate_stream(
            [Message(role="user", content="question")],
            "gpt-test",
            run_id="run-fallback",
        )
    ]

    trace_path = next((tmp_path / "traces").glob("**/*.jsonl"))
    raw = trace_path.read_text()
    records = [json.loads(line) for line in raw.splitlines()]
    hive_request = next(
        record
        for record in records
        if record["event"] == "request.attempt"
        and record["payload"].get("provider") == "hive"
    )
    completed = next(
        record for record in records if record["event"] == "call.completed"
    )
    assert hive_request["run_id"] == "run-fallback"
    assert completed["payload"]["text"] == "fallback answer"
    assert any(record["event"] == "provider.fallback" for record in records)
    assert "secret-hive-key" not in raw
    assert events[-1]["event"] == "provider_completed"
    await service.aclose()
    await hive.aclose()


@pytest.mark.asyncio
async def test_codex_stream_accepts_completed_tool_item_arguments(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            content=(
                b"event: response.output_item.done\n"
                b'data: {"item":{"type":"function_call","call_id":"call-2",'
                b'"output_index":0,"name":"analysis__run_technical_scan",'
                b'"arguments":"{\\"ticker\\":\\"TCS.NS\\"}"}}\n\n'
                b"event: response.completed\n"
                b'data: {"response":{}}\n\n'
            ),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = ChatGPTCodexService(
        client=client,
        credential_store=CodexCredentialStore(tmp_path / "credentials.json"),
    )
    service.credential_store.save(
        {"access_token": "access", "expires_at": 9_999_999_999}
    )

    events = [
        event
        async for event in service.generate_stream(
            [Message(role="user", content="Scan TCS")], "gpt-test"
        )
    ]

    chunks = [event["data"] for event in events if event["event"] == "chunk"]
    tool_call = chunks[0]["choices"][0]["delta"]["tool_calls"][0]
    assert tool_call["function"] == {
        "name": "analysis:run_technical_scan",
        "arguments": '{"ticker":"TCS.NS"}',
    }
    await service.aclose()


@pytest.mark.asyncio
async def test_codex_stream_assigns_indexes_by_call_id_when_missing(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            content=(
                b"event: response.output_item.added\n"
                b'data: {"item":{"type":"function_call","call_id":"call-a",'
                b'"name":"news__fetch_news"}}\n\n'
                b"event: response.function_call_arguments.done\n"
                b'data: {"call_id":"call-a","arguments":"{\\"ticker\\":\\"TCS\\"}"}\n\n'
                b"event: response.output_item.added\n"
                b'data: {"item":{"type":"function_call","call_id":"call-b",'
                b'"name":"analysis__run_technical_scan"}}\n\n'
                b"event: response.function_call_arguments.done\n"
                b'data: {"call_id":"call-b","arguments":"{\\"ticker\\":\\"INFY\\"}"}\n\n'
                b"event: response.completed\n"
                b'data: {"response":{}}\n\n'
            ),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = ChatGPTCodexService(
        client=client,
        credential_store=CodexCredentialStore(tmp_path / "credentials.json"),
    )
    service.credential_store.save(
        {"access_token": "access", "expires_at": 9_999_999_999}
    )

    events = [
        event
        async for event in service.generate_stream(
            [Message(role="user", content="Research TCS and INFY")], "gpt-test"
        )
    ]

    chunks = [event["data"] for event in events if event["event"] == "chunk"]
    assert [
        chunk["choices"][0]["delta"]["tool_calls"][0]["index"]
        for chunk in chunks
        if chunk["choices"][0]["delta"]["tool_calls"][0].get("id")
    ] == [0, 0, 1, 1]
    await service.aclose()


@pytest.mark.asyncio
async def test_codex_stream_emits_complete_gpt_style_tool_call(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            content=(
                b"event: response.output_item.added\n"
                b'data: {"item":{"type":"function_call","call_id":"call-1",'
                b'"output_index":0,"name":"news__fetch_news"}}\n\n'
                b"event: response.function_call_arguments.done\n"
                b'data: {"call_id":"call-1","output_index":0,'
                b'"arguments":"{\\"ticker\\":\\"HDFCBANK\\",\\"limit\\":5}"}\n\n'
                b"event: response.completed\n"
                b'data: {"response":{}}\n\n'
            ),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = ChatGPTCodexService(
        client=client,
        credential_store=CodexCredentialStore(tmp_path / "credentials.json"),
    )
    service.credential_store.save(
        {"access_token": "access", "expires_at": 9_999_999_999}
    )

    events = [
        event
        async for event in service.generate_stream(
            [Message(role="user", content="Find HDFC news")], "gpt-test"
        )
    ]

    chunks = [event["data"] for event in events if event["event"] == "chunk"]
    assert len(chunks) == 2
    assert chunks[-1]["choices"][0]["delta"]["tool_calls"][0]["function"] == {
        "arguments": '{"ticker":"HDFCBANK","limit":5}'
    }
    await service.aclose()


@pytest.mark.asyncio
async def test_missing_codex_credentials_falls_back_to_hive(tmp_path) -> None:
    requested_models = []

    class Fallback:
        def generate_stream(self, messages, model, **kwargs):
            requested_models.append(model)

            async def stream():
                yield {"event": "token", "data": "fallback"}

            return stream()

    service = ChatGPTCodexService(
        fallback=Fallback(),
        credential_store=CodexCredentialStore(tmp_path / "missing-codex.json"),
        fallback_model="hive-test",
    )

    events = [
        event
        async for event in service.generate_stream(
            [Message(role="user", content="hello")], "gpt-test"
        )
    ]

    assert events[-1] == {"event": "token", "data": "fallback"}
    assert requested_models == ["hive-test"]


@pytest.mark.asyncio
async def test_partial_codex_stream_does_not_append_fallback(tmp_path) -> None:
    class Fallback:
        def generate_stream(self, messages, model, **kwargs):
            async def stream():
                yield {"event": "token", "data": "wrong"}

            return stream()

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                content=b'event: response.output_text.delta\ndata: {"delta":"partial"}\n\n',
            )
        )
    )
    service = ChatGPTCodexService(
        client=client,
        fallback=Fallback(),
        credential_store=CodexCredentialStore(tmp_path / "credentials.json"),
    )
    service.credential_store.save(
        {"access_token": "access", "expires_at": 9_999_999_999}
    )

    with pytest.raises(ChatGPTCodexError, match="incomplete ChatGPT"):
        [
            event
            async for event in service.generate_stream(
                [Message(role="user", content="hello")], "gpt-test"
            )
        ]
