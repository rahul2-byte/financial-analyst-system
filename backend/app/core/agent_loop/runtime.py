"""A bounded, resumable model/tool loop independent of terminal rendering."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.core.agent_loop.model_events import (
    merge_chunk_tool_calls,
    result_payload,
    sanitize_tool_calls,
)
from app.core.diagnostics import diagnostic_payload, diagnostics_enabled
from app.core.resources import RuntimeResources
from app.core.skills import SkillPackage, SkillRegistry
from app.core.tools.tool_system import initialize_tool_system
from app.events.models import (
    ApprovalRequested,
    ClarificationRequested,
    EventFactory,
    ModelRequestStarted,
    ModelResponseCompleted,
    ProviderAttemptStarted,
    ProviderCompleted,
    ProviderFailed,
    ProviderRetrying,
    ProviderStreamStarted,
    ResearchEvent,
    RunCancelled,
    RunCompleted,
    RunFailed,
    RunStarted,
    SkillSelected,
    SourcesUpdated,
    StageStarted,
    TextDelta,
    ToolCompleted,
    ToolFailed,
    ToolProgress,
    ToolStarted,
)
from app.models.request_models import Message

logger = logging.getLogger(__name__)

_EVIDENCE_TOOLS = {
    "data:fetch_stock_data",
    "data:fetch_fundamentals",
    "news:fetch_news",
    "macro:fetch_macro_data",
    "analysis:run_fundamental_scan",
    "analysis:run_technical_scan",
}
_PARTIAL_RESPONSE_MIN_CHARS = 200


class ModelStream(Protocol):
    def generate_stream(
        self, messages: list[Message], model: str, **kwargs: Any
    ) -> AsyncIterator[dict[str, Any]]: ...


class ToolRunner(Protocol):
    def definitions(self) -> list[dict[str, Any]]: ...

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any: ...


class RegistryToolRunner:
    """Typed boundary around the existing registry/executor compatibility API."""

    def __init__(self, registry: Any, executor: Any, resources: RuntimeResources | None = None) -> None:
        self.registry = registry
        self.executor = executor
        self.resources = resources
        self._ohlcv_by_ticker: dict[str, list[dict[str, Any]]] = {}
        self._fundamentals_by_ticker: dict[str, dict[str, Any]] = {}
        initialize_tool_system()

    def definitions(self) -> list[dict[str, Any]]:
        executable = set(getattr(self.executor, "_handlers", {}))
        executable.add("interaction:ask_user")
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.full_name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self.registry.list_tools()
            if tool.full_name in executable
            and not tool.name.startswith("submit_")
        ]

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "analysis:run_fundamental_scan":
            ticker = str(arguments.get("ticker", "")).strip()
            cached_fundamentals = (
                self._fundamentals_by_ticker.get(ticker) if ticker else None
            )
            if cached_fundamentals is None and len(self._fundamentals_by_ticker) == 1:
                cached_fundamentals = next(iter(self._fundamentals_by_ticker.values()))
            if cached_fundamentals is None and ticker:
                fetched = await asyncio.to_thread(
                    self._resources().yf_fetcher.fetch_company_fundamentals,
                    ticker,
                )
                if isinstance(fetched, dict) and "error" not in fetched:
                    cached_fundamentals = fetched
                    self._fundamentals_by_ticker[
                        str(fetched.get("ticker") or ticker)
                    ] = fetched
            if cached_fundamentals:
                arguments = {**arguments, "raw_data": cached_fundamentals}
        if name == "analysis:run_technical_scan":
            ticker = str(arguments.get("ticker", "")).strip()
            cached = self._ohlcv_by_ticker.get(ticker) if ticker else None
            if cached is None and not ticker and len(self._ohlcv_by_ticker) == 1:
                cached = next(iter(self._ohlcv_by_ticker.values()))
            if cached:
                arguments = {**arguments, "ohlcv_data": cached}
            elif arguments.get("ohlcv_data"):
                pass
            elif not ticker:
                return {
                    "success": False,
                    "error": "No OHLCV data or ticker provided; fetch market data first",
                    "retryable": True,
                }
            else:
                runtime_resources = self._resources()
                fetched = await asyncio.to_thread(
                    runtime_resources.yf_fetcher.fetch_stock_price,
                    ticker,
                    str(arguments.get("period", "1y")),
                    str(arguments.get("interval", "1d")),
                )
                data = fetched.get("data") if isinstance(fetched, dict) else None
                if not data:
                    return {"success": False, "error": "No OHLCV data returned for ticker"}
                self._ohlcv_by_ticker[ticker] = data
                arguments = {**arguments, "ohlcv_data": data}
        if name in {"data:fetch_stock_data", "data:fetch_fundamentals", "news:fetch_news"}:
            runtime_resources = self._resources()

            if name == "data:fetch_stock_data":
                value = await asyncio.to_thread(
                    runtime_resources.yf_fetcher.fetch_stock_price,
                    str(arguments["ticker"]),
                    str(arguments.get("period", "1y")),
                    str(arguments.get("interval", "1d")),
                )
                rows = value.get("data") if isinstance(value, dict) else None
                if not rows:
                    return {"success": False, "error": "No evidence returned for data:fetch_stock_data"}
                ticker = str(value.get("ticker") or arguments["ticker"])
                self._ohlcv_by_ticker[ticker] = rows
                value = {
                    "ticker": ticker,
                    "period": value.get("period", arguments.get("period", "1y")),
                    "interval": value.get("interval", arguments.get("interval", "1d")),
                    "row_count": len(rows),
                    "period_return_pct": _period_return_pct(rows[0], rows[-1]),
                    "first": rows[0],
                    "latest": rows[-1],
                }
            elif name == "data:fetch_fundamentals":
                value = await asyncio.to_thread(
                    runtime_resources.yf_fetcher.fetch_company_fundamentals,
                    str(arguments["ticker"]),
                )
                if isinstance(value, dict) and "error" not in value:
                    ticker = str(value.get("ticker") or arguments["ticker"])
                    self._fundamentals_by_ticker[ticker] = value
            else:
                articles = await asyncio.to_thread(
                    runtime_resources.yf_fetcher.fetch_news,
                    str(arguments["ticker"]),
                    int(arguments.get("limit", 10)),
                )
                value = [
                    article.model_dump(mode="json")
                    if hasattr(article, "model_dump")
                    else dict(article)
                    for article in articles
                ]
            if not value:
                return {
                    "success": False,
                    "error": f"No evidence returned for {name}",
                }
            return {"success": True, "data": value}
        handler_result = getattr(self.executor, "execute_handler", None)
        if handler_result is not None:
            return (await handler_result(name, arguments)).to_dict()
        return await self.executor.execute(name, arguments)

    def _resources(self) -> RuntimeResources:
        if self.resources is not None:
            return self.resources
        from app.core.node_resources import resources as legacy_resources

        return RuntimeResources(
            llm_service=legacy_resources.llm_service,
            yf_fetcher=legacy_resources.yf_fetcher,
        )


class AgentLoopError(RuntimeError):
    """A controlled runtime failure suitable for user-facing rendering."""


@dataclass(frozen=True)
class AgentLoopConfig:
    max_rounds: int = 12
    max_tool_calls: int = 24
    model: str = "reasoning"
    mode: str = "guided"
    max_tokens: int = 2048


class AgentLoop:
    """Run a conversation until the model answers, pauses, or reaches a limit."""

    def __init__(
        self,
        model_client: ModelStream,
        tool_runner: ToolRunner,
        *,
        config: AgentLoopConfig | None = None,
        skill_registry: SkillRegistry | None = None,
    ) -> None:
        self.model_client = model_client
        self.tool_runner = tool_runner
        self.config = config or AgentLoopConfig()
        self.skill_registry = skill_registry

    async def run(
        self,
        messages: list[Message],
        *,
        conversation_id: UUID,
        approved_tool_ids: set[str] | None = None,
        input_queue: asyncio.Queue[Message] | None = None,
        checkpoint_writer: Any | None = None,
        message_writer: Any | None = None,
    ) -> AsyncIterator[ResearchEvent]:
        started = time.perf_counter()
        factory = EventFactory(conversation_id)
        approved = approved_tool_ids or set()
        history = list(messages)
        selected_skills = self._select_skills(history)
        history = _add_skill_context(history, selected_skills)
        tool_calls_seen = 0
        failed_tools = 0
        successful_tools = 0
        failed_evidence_tools = 0
        successful_evidence_tools = 0
        evidence_warning_added = False
        completed_tool_ids = {
            message.tool_call_id
            for message in history
            if message.role == "tool" and message.tool_call_id
        }
        resumed_assistant = (
            next(
                (
                    message
                    for message in reversed(history)
                    if message.role == "assistant"
                    and message.tool_calls
                    and any(
                        _tool_call_identity(call)[1] not in completed_tool_ids
                        for call in message.tool_calls
                    )
                ),
                None,
            )
            if approved
            else None
        )
        yield factory.make(RunStarted, query=_last_user_query(history))
        for skill in selected_skills:
            yield factory.make(
                SkillSelected,
                skill_id=skill.manifest.id,
                version=skill.manifest.version,
                package_hash=skill.sha256,
            )
        yield factory.make(StageStarted, stage="agent", label="Preparing research")

        try:
            for round_number in range(1, self.config.max_rounds + 1):
                if diagnostics_enabled():
                    logger.debug(
                        "agent round start run_id=%s round=%s messages=%s tools=%s",
                        factory.run_id,
                        round_number,
                        len(history),
                        tool_calls_seen,
                    )
                self._drain_input_queue(history, input_queue)
                assistant = resumed_assistant
                resumed_assistant = None
                if assistant is None:
                    yield factory.make(
                        ModelRequestStarted,
                        model=self.config.model,
                        round=round_number,
                    )
                    streamed_text: list[str] = []
                    try:
                        async for item in self._stream_model(
                            history, factory, round_number, selected_skills
                        ):
                            if isinstance(item, TextDelta):
                                streamed_text.append(item.text)
                                yield item
                            elif isinstance(item, (ProviderAttemptStarted, ProviderRetrying,
                                                   ProviderStreamStarted, ProviderCompleted,
                                                   ProviderFailed)):
                                yield item
                            else:
                                assistant = item
                    except Exception as exc:
                        partial_text = "".join(streamed_text)
                        if len(partial_text.strip()) < _PARTIAL_RESPONSE_MIN_CHARS:
                            raise
                        logger.warning(
                            "Provider stream ended after substantive output; preserving partial response",
                            exc_info=True,
                        )
                        yield factory.make(
                            ProviderFailed,
                            attempts=1,
                            phase="stream",
                            message=str(exc),
                        )
                        assistant = Message(
                            role="assistant",
                            name="partial_provider_response",
                            content=partial_text,
                        )
                    if assistant is None:
                        raise AgentLoopError("model stream ended without a response")
                    history.append(assistant)
                    if message_writer:
                        message_writer(assistant)
                    yield factory.make(
                        ModelResponseCompleted,
                        round=round_number,
                        has_tool_calls=bool(assistant.tool_calls),
                    )

                if not assistant.tool_calls:
                    terminal_status = (
                        "insufficient_data"
                        if failed_tools and not successful_tools
                        else "partial"
                        if failed_tools or assistant.name == "partial_provider_response"
                        else "success"
                    )
                    yield factory.make(
                        RunCompleted,
                        terminal_status=terminal_status,
                        duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    )
                    return

                for call in assistant.tool_calls:
                    tool_calls_seen += 1
                    if tool_calls_seen > self.config.max_tool_calls:
                        raise AgentLoopError("tool-call limit reached for this run")
                    try:
                        name, call_id, arguments = _tool_call_parts(call)
                    except AgentLoopError as exc:
                        name, call_id = _tool_call_identity(call)
                        message = str(exc)
                        if name == "interaction:ask_user":
                            # A malformed clarification call must not trigger
                            # another model round. Pause safely with a
                            # deterministic question instead of losing the run.
                            question = (
                                "Please clarify the company or ticker, timeframe, "
                                "and investment or research objective."
                            )
                            if checkpoint_writer:
                                checkpoint_writer(
                                    {
                                        "messages": [
                                            message.model_dump(mode="json")
                                            for message in history
                                        ],
                                        "tool_call_id": call_id,
                                        "tool_name": name,
                                        "arguments": {"question": question},
                                        "status": "awaiting_clarification",
                                    }
                                )
                            yield factory.make(ClarificationRequested, prompt=question)
                            return
                        history.append(
                            Message(
                                role="tool",
                                content=json.dumps({"success": False, "error": message}),
                                tool_call_id=call_id,
                            )
                        )
                        if message_writer:
                            message_writer(history[-1])
                        yield factory.make(
                            ToolFailed,
                            tool=name or "unknown",
                            tool_id=call_id,
                            message=message,
                        )
                        continue
                    if call_id in completed_tool_ids:
                        continue
                    if name == "interaction:ask_user":
                        question = str(arguments.get("question", "Please clarify the request."))
                        if checkpoint_writer:
                            checkpoint_writer(
                                {
                                    "messages": [message.model_dump(mode="json") for message in history],
                                    "tool_call_id": call_id,
                                    "tool_name": name,
                                    "arguments": arguments,
                                    "status": "awaiting_clarification",
                                }
                            )
                        yield factory.make(ClarificationRequested, prompt=question)
                        return
                    if self._needs_approval(name, call_id, approved):
                        if checkpoint_writer:
                            checkpoint_writer(
                                {
                                    "messages": [
                                        message.model_dump(mode="json")
                                        for message in history
                                    ],
                                    "tool_call_id": call_id,
                                    "tool_name": name,
                                    "arguments": arguments,
                                    "status": "awaiting_approval",
                                }
                            )
                        yield factory.make(
                            ApprovalRequested,
                            prompt=f"FIN-AI wants to run {name}.",
                            details=json.dumps(arguments, sort_keys=True),
                        )
                        return

                    yield factory.make(ToolStarted, tool=name, tool_id=call_id)
                    yield factory.make(
                        ToolProgress,
                        tool=name,
                        tool_id=call_id,
                        message=f"Running {name}",
                    )
                    tool_started = time.perf_counter()
                    if diagnostics_enabled():
                        logger.debug(
                            "tool call start run_id=%s tool=%s tool_id=%s arguments=%s",
                            factory.run_id,
                            name,
                            call_id,
                            diagnostic_payload(arguments)
                            if os.environ.get("FINAI_DIAGNOSTICS") == "payloads"
                            else "omitted",
                        )
                    try:
                        result = await self.tool_runner.execute(name, arguments)
                        payload = result_payload(result)
                    except asyncio.CancelledError:
                        yield factory.make(RunCancelled, reason="cancelled by user")
                        return
                    except Exception as exc:
                        payload = {"success": False, "error": str(exc)}
                        logger.exception("tool call raised tool=%s tool_id=%s", name, call_id)
                    if diagnostics_enabled():
                        logger.debug(
                            "tool call end run_id=%s tool=%s tool_id=%s duration_ms=%.1f success=%s",
                            factory.run_id,
                            name,
                            call_id,
                            (time.perf_counter() - tool_started) * 1000,
                            payload.get("success", True),
                        )

                    if payload.get("success", True) is False:
                        failed_tools += 1
                        if name in _EVIDENCE_TOOLS and not payload.get("retryable", False):
                            failed_evidence_tools += 1
                        message = str(payload.get("error", "tool failed"))
                        if name in _EVIDENCE_TOOLS and not payload.get("retryable", False) and not evidence_warning_added:
                            history.append(
                                Message(
                                    role="system",
                                    content=(
                                        "Evidence integrity warning: one or more evidence tools failed. "
                                        "Do not invent prices, ratios, percentages, dates, news, targets, or sources. "
                                        "Use only values present in successful tool results. Label the final response "
                                        "as partial or insufficient-data and list the missing evidence explicitly."
                                    ),
                                )
                            )
                            evidence_warning_added = True
                            if message_writer:
                                message_writer(history[-1])
                        history.append(
                            Message(
                                role="tool",
                            content=json.dumps(payload, default=str),
                                tool_call_id=call_id,
                            )
                        )
                        if message_writer:
                            message_writer(history[-1])
                        yield factory.make(ToolFailed, tool=name, tool_id=call_id, message=message)
                    else:
                        successful_tools += 1
                        if name in _EVIDENCE_TOOLS:
                            successful_evidence_tools += 1
                        history.append(
                            Message(
                                role="tool",
                                content=json.dumps(payload, default=str),
                                tool_call_id=call_id,
                            )
                        )
                        if message_writer:
                            message_writer(history[-1])
                        yield factory.make(
                            ToolCompleted,
                            tool=name,
                            tool_id=call_id,
                            detail=_summary(payload),
                            duration_ms=round((time.perf_counter() - tool_started) * 1000, 2),
                        )
                        sources = payload.get("sources")
                        if isinstance(sources, list) and all(
                            isinstance(source, dict) for source in sources
                        ):
                            yield factory.make(SourcesUpdated, sources=sources)
                    self._drain_input_queue(history, input_queue)
                if failed_evidence_tools and not successful_evidence_tools:
                    message = (
                        "I couldn't produce a reliable analysis because the required "
                        "evidence tools returned no usable data. Retry the request or "
                        "provide a ticker and data source; no financial figures were inferred."
                    )
                    yield factory.make(TextDelta, text=message)
                    yield factory.make(
                        RunCompleted,
                        terminal_status="insufficient_data",
                        duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    )
                    return
                continue
            raise AgentLoopError("agent round limit reached for this run")
        except asyncio.CancelledError:
            yield factory.make(RunCancelled, reason="cancelled by user")
        except Exception as exc:
            logger.exception("Agent loop failed")
            yield factory.make(RunFailed, message=str(exc), category="runtime")

    def _select_skills(self, messages: list[Message]) -> list[SkillPackage]:
        if self.skill_registry is None:
            return []
        return self.skill_registry.select(_last_user_query(messages))

    def _tool_definitions(self, skills: list[SkillPackage]) -> list[dict[str, Any]]:
        definitions = self.tool_runner.definitions()
        base_tools = {
            "data:fetch_stock_data",
            "data:fetch_fundamentals",
            "news:fetch_news",
            "macro:fetch_macro_data",
            "analysis:run_fundamental_scan",
            "analysis:run_technical_scan",
            "interaction:ask_user",
        }
        if not skills:
            return [
                definition
                for definition in definitions
                if definition.get("function", {}).get("name") in base_tools
            ]
        allowed = {
            tool
            for skill in skills
            for tool in skill.manifest.allowed_tools
        }
        if any(skill.manifest.id == "research-planning" for skill in skills):
            allowed.update(base_tools)
        if not allowed:
            allowed = base_tools
        return [
            definition
            for definition in definitions
            if definition.get("function", {}).get("name") in allowed
        ]

    async def _stream_model(
        self,
        messages: list[Message],
        factory: EventFactory,
        round_number: int,
        skills: list[SkillPackage],
    ) -> AsyncIterator[
        TextDelta
        | Message
        | ProviderAttemptStarted
        | ProviderRetrying
        | ProviderStreamStarted
        | ProviderCompleted
        | ProviderFailed
    ]:
        text: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        async for event in self.model_client.generate_stream(
            messages,
            self.config.model,
            tools=self._tool_definitions(skills),
            max_tokens=(
                self.config.max_tokens
                if any(message.role == "tool" for message in messages)
                else min(self.config.max_tokens, 512)
            ),
            temperature=0.1,
        ):
            event_name = event.get("event")
            if event_name == "provider_attempt_started":
                yield factory.make(
                    ProviderAttemptStarted,
                    attempt=int(event.get("data", {}).get("attempt", 1)),
                )
            elif event_name == "provider_retrying":
                data = event.get("data", {})
                yield factory.make(
                    ProviderRetrying,
                    attempt=int(data.get("attempt", 1)),
                    status_code=data.get("status_code"),
                    delay_ms=float(data.get("delay_ms", 0)),
                    reason=str(data.get("reason", "transient provider failure")),
                )
            elif event_name == "provider_stream_started":
                data = event.get("data", {})
                yield factory.make(
                    ProviderStreamStarted,
                    attempt=int(data.get("attempt", 1)),
                    first_byte_ms=float(data.get("first_byte_ms", 0)),
                )
            elif event_name == "provider_completed":
                data = event.get("data", {})
                yield factory.make(
                    ProviderCompleted,
                    attempts=int(data.get("attempts", 1)),
                    duration_ms=float(data.get("duration_ms", 0)),
                    first_token_ms=data.get("first_token_ms"),
                )
            elif event_name == "provider_failed":
                data = event.get("data", {})
                yield factory.make(
                    ProviderFailed,
                    attempts=int(data.get("attempts", 1)),
                    phase=str(data.get("phase", "unknown")),
                    status_code=data.get("status_code"),
                    message=str(data.get("message", "Hive provider failed")),
                )
            elif event_name == "token":
                chunk = str(event.get("data", ""))
                if chunk:
                    for offset in range(0, len(chunk), 64):
                        part = chunk[offset : offset + 64]
                        text.append(part)
                        yield factory.make(TextDelta, text=part)
                        # Give the TUI a scheduling point between coalesced
                        # provider frames without inventing progress.
                        await asyncio.sleep(0)
                raw_chunk = event.get("chunk")
                merge_chunk_tool_calls(calls, raw_chunk)
            elif event.get("event") == "chunk":
                chunk_payload = event.get("data")
                if isinstance(chunk_payload, dict):
                    choices = chunk_payload.get("choices", [])
                    delta = choices[0].get("delta", {}) if choices else {}
                    content = delta.get("content") if isinstance(delta, dict) else None
                    if content:
                        for offset in range(0, len(str(content)), 64):
                            part = str(content)[offset : offset + 64]
                            text.append(part)
                            yield factory.make(TextDelta, text=part)
                            await asyncio.sleep(0)
                merge_chunk_tool_calls(calls, chunk_payload)
        tool_calls = sanitize_tool_calls([calls[index] for index in sorted(calls)]) or None
        yield Message(role="assistant", content="".join(text), tool_calls=tool_calls)

    def _needs_approval(self, name: str, call_id: str, approved: set[str]) -> bool:
        if call_id in approved or self.config.mode == "autonomous":
            return False
        return name.split(":", 1)[0] in {"data", "news", "research", "market"}

    @staticmethod
    def _drain_input_queue(history: list[Message], queue: asyncio.Queue[Message] | None) -> None:
        if queue is None:
            return
        while True:
            try:
                history.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                return


def _tool_call_parts(call: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    function = call.get("function", {})
    name = str(function.get("name") or call.get("name") or "")
    call_id = str(call.get("id") or f"call-{name}")
    raw_arguments = function.get("arguments", call.get("arguments", {}))
    if isinstance(raw_arguments, str):
        try:
            raw_arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise AgentLoopError(f"invalid arguments for {name}: {exc}") from exc
    if not isinstance(raw_arguments, dict):
        raise AgentLoopError(f"arguments for {name} must be an object")
    return name, call_id, raw_arguments


def _tool_call_identity(call: dict[str, Any]) -> tuple[str, str]:
    """Return safe display metadata when a streamed call has invalid arguments."""
    function = call.get("function", {})
    name = str(function.get("name") or call.get("name") or "unknown")
    call_id = str(call.get("id") or f"call-{name}")
    return name, call_id




def _summary(payload: dict[str, Any]) -> str:
    if "summary" in payload:
        return str(payload["summary"])
    if "data" in payload and isinstance(payload["data"], dict):
        return f"received {len(payload['data'])} fields"
    return "completed"


def _period_return_pct(first: dict[str, Any], latest: dict[str, Any]) -> float | None:
    first_close = first.get("Close", first.get("close"))
    latest_close = latest.get("Close", latest.get("close"))
    if not isinstance(first_close, (int, float)) or not first_close:
        return None
    if not isinstance(latest_close, (int, float)):
        return None
    return round((latest_close / first_close - 1) * 100, 2)


def _last_user_query(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def _add_skill_context(
    messages: list[Message], skills: list[SkillPackage]
) -> list[Message]:
    if not skills:
        return messages
    prompt = "\n\n---\n\n".join(skill.prompt() for skill in skills)
    for index, message in enumerate(messages):
        if message.role == "system":
            messages[index] = Message(role="system", content=f"{message.content}\n\n{prompt}")
            return messages
    return [Message(role="system", content=prompt), *messages]
