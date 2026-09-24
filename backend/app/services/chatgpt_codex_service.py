"""Experimental OpenCode-style ChatGPT OAuth provider."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import time
import urllib.parse
import webbrowser
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from app.core.model_call_trace import (
    ModelCallTrace,
    call_started,
    capture_stream,
    safe_endpoint,
)
from app.models.request_models import Message
from app.services.llm_interface import LLMServiceInterface


class OAuthStateError(RuntimeError):
    """The OAuth callback did not match the active login attempt."""


class ChatGPTCodexError(RuntimeError):
    """A bounded ChatGPT Codex provider failure."""


class CodexCredentialStore:
    """Small owner-only JSON credential store for local development."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()

    def load(self) -> dict[str, Any] | None:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def save(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        self.path.chmod(0o600)

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)


class ChatGPTCodexService(LLMServiceInterface):
    """Use the OpenCode-compatible Codex endpoint with Hive fallback."""

    DEFAULT_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
    DEFAULT_ISSUER = "https://auth.openai.com"
    DEFAULT_ENDPOINT = "https://chatgpt.com/backend-api/codex/responses"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        fallback: LLMServiceInterface | Any | None = None,
        credential_store: CodexCredentialStore | None = None,
        client_id: str = DEFAULT_CLIENT_ID,
        issuer: str = DEFAULT_ISSUER,
        authorization_endpoint: str | None = None,
        token_endpoint: str | None = None,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout_seconds: float = 60.0,
        fallback_model: str = "zai-org/glm-5.3-flash",
    ) -> None:
        self._client = client or httpx.AsyncClient()
        self.fallback = fallback
        self.credential_store = credential_store or CodexCredentialStore(
            Path.home() / ".config" / "finai" / "chatgpt-codex.json"
        )
        self.client_id = client_id
        self.issuer = issuer.rstrip("/")
        self.authorization_endpoint = authorization_endpoint or (
            f"{self.issuer}/oauth/authorize"
        )
        self.token_endpoint = token_endpoint or f"{self.issuer}/oauth/token"
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.fallback_model = fallback_model
        self.pending_state: str | None = None
        self.pending_verifier: str | None = None
        self.last_telemetry: dict[str, Any] = {}

    def authorization_url(
        self, redirect_uri: str = "http://localhost:1455/auth/callback"
    ) -> str:
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        self.pending_verifier = verifier
        self.pending_state = secrets.token_urlsafe(32)
        query = urllib.parse.urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid profile email offline_access",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "id_token_add_organizations": "true",
                "codex_cli_simplified_flow": "true",
                "state": self.pending_state,
                "originator": "opencode",
            }
        )
        return f"{self.authorization_endpoint}?{query}"

    def validate_callback(self, code: str, state: str) -> tuple[str, str]:
        if (
            not code
            or not self.pending_state
            or not secrets.compare_digest(state, self.pending_state)
        ):
            raise OAuthStateError("invalid ChatGPT OAuth callback state")
        if not self.pending_verifier:
            raise OAuthStateError("ChatGPT OAuth verifier is missing")
        verifier = self.pending_verifier
        self.pending_state = None
        self.pending_verifier = None
        return code, verifier

    async def exchange_code(
        self, code: str, verifier: str, redirect_uri: str
    ) -> dict[str, Any]:
        response = await self._client.post(
            self.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise ChatGPTCodexError("ChatGPT OAuth token response is invalid")
        payload["expires_at"] = time.time() + float(payload.get("expires_in", 3600))
        self.credential_store.save(payload)
        return payload

    async def login(
        self, redirect_host: str = "127.0.0.1", redirect_port: int = 1455
    ) -> dict[str, Any]:
        redirect_uri = f"http://localhost:{redirect_port}/auth/callback"
        url = self.authorization_url(redirect_uri)
        loop = asyncio.get_running_loop()
        result: asyncio.Future[dict[str, Any]] = loop.create_future()

        async def callback(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            try:
                request = (await reader.read(8192)).decode(errors="replace")
                target = request.split(" ", 2)[1]
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(target).query)
                code = query.get("code", [""])[0]
                state = query.get("state", [""])[0]
                code, verifier = self.validate_callback(code, state)
                credentials = await self.exchange_code(code, verifier, redirect_uri)
                if not result.done():
                    result.set_result(credentials)
                body = b"FIN-AI ChatGPT login complete. You may close this tab."
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n" + body
                )
                await writer.drain()
            except Exception as exc:  # noqa: BLE001 - callback must resolve login safely
                if not result.done():
                    result.set_exception(exc)
                writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\nLogin failed")
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(callback, redirect_host, redirect_port)
        try:
            webbrowser.open(url)
            return await asyncio.wait_for(result, timeout=self.timeout_seconds * 2)
        finally:
            server.close()
            await server.wait_closed()

    async def refresh(self, credentials: dict[str, Any]) -> dict[str, Any]:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise ChatGPTCodexError("ChatGPT refresh token is missing")
        response = await self._client.post(
            self.token_endpoint,
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "refresh_token": refresh_token,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise ChatGPTCodexError("ChatGPT refresh response is invalid")
        merged = {**credentials, **payload}
        merged["expires_at"] = time.time() + float(payload.get("expires_in", 3600))
        self.credential_store.save(merged)
        return merged

    async def _credentials(self) -> dict[str, Any] | None:
        credentials = self.credential_store.load()
        if not credentials:
            return None
        if float(credentials.get("expires_at", 0)) <= time.time() + 60:
            try:
                credentials = await self.refresh(credentials)
            except (httpx.HTTPError, ChatGPTCodexError):
                self.credential_store.delete()
                return None
        return credentials

    async def _fallback_stream(
        self, messages: list[Message], model: str, reason: str, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        self.last_telemetry = {"provider": "chatgpt_codex", "fallback_reason": reason}
        trace = kwargs.get("_model_call_trace")
        if isinstance(trace, ModelCallTrace):
            trace.write("provider.fallback", {"reason": reason})
        yield {
            "event": "provider_failed",
            "data": {
                "provider": "chatgpt_codex",
                "message": reason,
                "partial_output": False,
                "fallback": True,
            },
        }
        if self.fallback is None:
            raise ChatGPTCodexError(reason)
        async for event in self.fallback.generate_stream(
            messages, self.fallback_model, **kwargs
        ):
            yield event

    def generate_stream(
        self, messages: list[Message], model: str, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        async def stream() -> AsyncGenerator[dict[str, Any], None]:
            trace = kwargs.get("_model_call_trace")
            owns_trace = not isinstance(trace, ModelCallTrace)
            if owns_trace:
                trace = ModelCallTrace.create(
                    provider="chatgpt_codex",
                    model=model,
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
            source = self._generate_stream_events(messages, model, traced_kwargs)
            if owns_trace and isinstance(trace, ModelCallTrace):
                async for event in capture_stream(trace, source):
                    yield event
            else:
                async for event in source:
                    yield event

        return stream()

    async def _generate_stream_events(
        self, messages: list[Message], model: str, kwargs: dict[str, Any]
    ) -> AsyncGenerator[dict[str, Any], None]:
        credentials = await self._credentials()
        if credentials is None:
            async for event in self._fallback_stream(
                messages, model, "ChatGPT credentials unavailable", **kwargs
            ):
                yield event
            return
        stream_started = False
        try:
            async for event in self._stream_request(
                credentials, messages, model, **kwargs
            ):
                stream_started = stream_started or event.get("event") in {
                    "provider_stream_started",
                    "token",
                    "chunk",
                }
                yield event
        except (ChatGPTCodexError, httpx.HTTPError, TimeoutError) as exc:
            if stream_started:
                raise
            async for event in self._fallback_stream(
                messages, model, str(exc), **kwargs
            ):
                yield event

    async def _stream_request(
        self,
        credentials: dict[str, Any],
        messages: list[Message],
        model: str,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        payload: dict[str, Any] = {
            "model": model,
            "input": _responses_input(messages),
            "stream": True,
            "store": False,
        }
        if kwargs.get("tools"):
            payload["tools"] = [_response_tool(tool) for tool in kwargs["tools"]]
        trace = kwargs.get("_model_call_trace")
        if isinstance(trace, ModelCallTrace):
            trace.write(
                "request.attempt",
                {
                    "attempt": 1,
                    "provider": "chatgpt_codex",
                    "endpoint": safe_endpoint(self.endpoint),
                    "request_body": payload,
                },
            )
        headers = {
            "Authorization": f"Bearer {credentials['access_token']}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        account_id = _chatgpt_account_id(str(credentials["access_token"]))
        if account_id:
            headers["ChatGPT-Account-Id"] = account_id
        yield {
            "event": "provider_attempt_started",
            "data": {"attempt": 1, "provider": "chatgpt_codex"},
        }
        started = time.perf_counter()
        first_token_ms: float | None = None
        saw_stream = False
        current_event = ""
        tool_indexes: dict[str, int] = {}
        async with self._client.stream(
            "POST",
            self.endpoint,
            json=payload,
            headers=headers,
            timeout=self.timeout_seconds,
        ) as response:
            if response.status_code != 200:
                body = (await response.aread()).decode(errors="replace")
                trace = kwargs.get("_model_call_trace")
                if isinstance(trace, ModelCallTrace):
                    trace.write(
                        "response.http_error",
                        {
                            "attempt": 1,
                            "status_code": response.status_code,
                            "body": body,
                        },
                    )
                raise ChatGPTCodexError(
                    f"ChatGPT HTTP {response.status_code}: {body[:200]}"
                )
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                if not saw_stream:
                    saw_stream = True
                    yield {
                        "event": "provider_stream_started",
                        "data": {"attempt": 1, "provider": "chatgpt_codex"},
                    }
                event_name, data = _parse_sse_line(line)
                if event_name:
                    current_event = event_name
                    continue
                if not data:
                    continue
                if current_event == "response.output_text.delta":
                    delta = data.get("delta", "")
                    if delta:
                        if first_token_ms is None:
                            first_token_ms = round(
                                (time.perf_counter() - started) * 1000, 2
                            )
                        yield {"event": "token", "data": delta}
                elif current_event == "response.output_item.added":
                    item = data.get("item", {})
                    if item.get("type") == "function_call":
                        yield {
                            "event": "chunk",
                            "data": _tool_chunk(item, _tool_index(item, tool_indexes)),
                        }
                elif current_event == "response.function_call_arguments.delta":
                    yield {
                        "event": "chunk",
                        "data": _tool_argument_chunk(
                            data, _tool_index(data, tool_indexes)
                        ),
                    }
                elif current_event == "response.function_call_arguments.done":
                    yield {
                        "event": "chunk",
                        "data": _tool_argument_done_chunk(
                            data, _tool_index(data, tool_indexes)
                        ),
                    }
                elif current_event == "response.output_item.done":
                    item = data.get("item", {})
                    if item.get("type") == "function_call":
                        yield {
                            "event": "chunk",
                            "data": _tool_chunk(item, _tool_index(item, tool_indexes)),
                        }
                elif current_event == "response.completed":
                    response_data = data.get("response", data)
                    usage = response_data.get("usage")
                    yield {
                        "event": "provider_completed",
                        "data": {
                            "provider": "chatgpt_codex",
                            "attempts": 1,
                            "duration_ms": round(
                                (time.perf_counter() - started) * 1000, 2
                            ),
                            "first_token_ms": first_token_ms,
                            "model_id": model,
                            "usage": _normalize_usage(usage),
                        },
                    }
                    return
                elif current_event == "response.failed":
                    raise ChatGPTCodexError("ChatGPT response failed")
        raise ChatGPTCodexError("incomplete ChatGPT response stream")

    async def generate(self, messages: list[Message], model: str, **kwargs: Any) -> str:
        parts: list[str] = []

        async def collect() -> str:
            stream = self.generate_stream(messages, model, **kwargs)
            try:
                async for event in stream:
                    if event.get("event") == "token":
                        parts.append(str(event.get("data", "")))
            finally:
                await stream.aclose()
            return "".join(parts)

        try:
            return await asyncio.wait_for(collect(), timeout=self.timeout_seconds)
        except TimeoutError as exc:
            raise ChatGPTCodexError(
                "ChatGPT generation exceeded total timeout"
            ) from exc

    async def generate_message(
        self, messages: list[Message], model: str, **kwargs: Any
    ) -> Message:
        return Message(
            role="assistant", content=await self.generate(messages, model, **kwargs)
        )

    async def check_health(self) -> bool:
        return self.credential_store.load() is not None

    async def aclose(self) -> None:
        if not self._client.is_closed:
            await self._client.aclose()
        if self.fallback is not None and hasattr(self.fallback, "aclose"):
            await self.fallback.aclose()


def _parse_sse_line(line: str) -> tuple[str, dict[str, Any] | None]:
    if line.startswith("event:"):
        return line[6:].strip(), None
    if not line.startswith("data:"):
        return "", None
    try:
        payload = json.loads(line[5:].strip())
    except json.JSONDecodeError as exc:
        raise ChatGPTCodexError("malformed ChatGPT SSE payload") from exc
    return "", payload if isinstance(payload, dict) else None


def _message_to_input(message: Message) -> dict[str, Any]:
    if message.role == "tool":
        return {
            "type": "function_call_output",
            "call_id": message.tool_call_id or "unknown",
            "output": message.content,
        }
    return {"role": message.role, "content": message.content}


def _responses_input(messages: list[Message]) -> list[dict[str, Any]]:
    """Translate internal chat history into paired Responses API items."""
    call_ids = {
        str(call.get("id") or call.get("call_id"))
        for message in messages
        if message.role == "assistant"
        for call in message.tool_calls or []
        if call.get("id") or call.get("call_id")
    }
    output_ids = {
        str(message.tool_call_id)
        for message in messages
        if message.role == "tool" and message.tool_call_id
    }
    paired_ids = call_ids & output_ids
    items: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool":
            if message.tool_call_id in paired_ids:
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id,
                        "output": message.content,
                    }
                )
            continue
        if message.role == "assistant" and message.tool_calls:
            if message.content:
                items.append({"role": "assistant", "content": message.content})
            for call in message.tool_calls:
                call_id = str(call.get("id") or call.get("call_id") or "")
                if call_id not in paired_ids:
                    continue
                function = call.get("function", call)
                arguments = function.get("arguments", "{}")
                if not isinstance(arguments, str):
                    arguments = json.dumps(arguments, separators=(",", ":"))
                items.append(
                    {
                        "type": "function_call",
                        "call_id": call_id,
                        "name": _external_tool_name(str(function.get("name", ""))),
                        "arguments": arguments,
                    }
                )
            continue
        items.append(_message_to_input(message))
    return items


def _external_tool_name(name: str) -> str:
    return name.replace(":", "__")


def _internal_tool_name(name: str) -> str:
    return name.replace("__", ":", 1)


def _response_tool(tool: dict[str, Any]) -> dict[str, Any]:
    function = tool.get("function", tool)
    return {
        "type": "function",
        "name": _external_tool_name(str(function.get("name", ""))),
        "description": function.get("description", ""),
        "parameters": function.get("parameters", {}),
    }


def _tool_index(data: dict[str, Any], indexes: dict[str, int]) -> int:
    output_index = data.get("output_index")
    if isinstance(output_index, int):
        return output_index
    call_id = data.get("call_id") or data.get("item_id") or data.get("id")
    key = str(call_id or "")
    if key not in indexes:
        indexes[key] = len(indexes)
    return indexes[key]


def _tool_chunk(item: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": index,
                            "id": item.get("call_id") or item.get("id"),
                            "type": "function",
                            "function": {
                                "name": _internal_tool_name(str(item.get("name", ""))),
                                "arguments": str(item.get("arguments", "")),
                            },
                        }
                    ]
                }
            }
        ]
    }


def _tool_argument_chunk(data: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": index,
                            "function": {"arguments": data.get("delta", "")},
                        }
                    ]
                }
            }
        ]
    }


def _tool_argument_done_chunk(data: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": index,
                            "id": data.get("call_id") or data.get("item_id"),
                            "function": {"arguments": data.get("arguments", "")},
                        }
                    ]
                }
            }
        ]
    }


def _normalize_usage(usage: Any) -> dict[str, int] | None:
    if not isinstance(usage, dict):
        return None
    return {
        "prompt_tokens": int(
            usage.get("input_tokens") or usage.get("prompt_tokens") or 0
        ),
        "completion_tokens": int(
            usage.get("output_tokens") or usage.get("completion_tokens") or 0
        ),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }


def _chatgpt_account_id(token: str) -> str | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        encoded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded).decode())
        auth = payload.get("https://api.openai.com/auth", {})
        value = auth.get("chatgpt_account_id")
        return str(value) if value else None
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None
