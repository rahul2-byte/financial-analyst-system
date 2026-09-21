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

from app.core.agent_loop.evidence import EvidenceAccounting
from app.core.agent_loop.model_streaming import ModelStreaming
from app.core.agent_loop.publication import (
    PublicationError,
    ReportParseError,
    parse_report_draft,
    publish_report,
    report_repair_instruction,
    report_validation_fallback,
)
from app.core.agent_loop.terminal_state import terminal_status
from app.core.agent_loop.tool_execution import ToolExecutor
from app.core.diagnostics import diagnostic_payload, diagnostics_enabled
from app.core.guardrails import assess_input_safety
from app.core.observability import observe
from app.core.prompts import PromptRegistry
from app.core.skills import SkillPackage, SkillRegistry
from app.core.ticker import parse_ticker
from app.events.models import (
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
    RouteDecisionMade,
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
from app.models.routing import ExecutionMode, ModelTier, NextAction, RoutePlan
from app.observability.tracing import set_current_span_attributes, span
from app.security.policy import redact_secrets

logger = logging.getLogger(__name__)

_EVIDENCE_TOOLS = {
    "data:fetch_stock_data",
    "data:fetch_fundamentals",
    "news:fetch_news",
    "analysis:run_fundamental_scan",
    "analysis:run_technical_scan",
    "analysis:get_technical_overview",
}
_PARTIAL_RESPONSE_MIN_CHARS = 200
_EVIDENCE_REQUIRED_SKILLS = {
    "fundamental-analysis",
    "technical-analysis",
    "equity-research",
    "report-synthesis",
}
_TICKER_TOOLS = {
    "data:fetch_stock_data",
    "data:fetch_fundamentals",
    "news:fetch_news",
    "analysis:run_fundamental_scan",
    "analysis:run_technical_scan",
    "analysis:get_technical_overview",
}
def _clarification_prompt(route: RoutePlan) -> str:
    if route.escalation_reason:
        return route.escalation_reason
    if route.reason and not route.reason.casefold().startswith("jev selected"):
        return route.reason
    return "Please clarify the request so I can continue safely."


def _report_repair_history(messages: list[Message]) -> list[Message]:
    """Keep report repair input free of completed or stale tool-call turns."""
    repair_instruction = next(
        (
            message
            for message in reversed(messages)
            if message.role == "system"
            and (
                message.prompt_key == "publication.report_repair"
            )
        ),
        None,
    )
    previous_draft = next(
        (
            message
            for message in reversed(messages)
            if message.role == "assistant"
            and bool(message.content.strip())
            and not message.tool_calls
        ),
        None,
    )
    retained = [
        message
        for message in messages
        if message.role in {"user", "system"}
        and message.prompt_key != "publication.report_repair"
    ]
    if previous_draft is not None:
        retained.append(previous_draft)
    if repair_instruction is not None:
        retained.append(repair_instruction)
    return retained


class ModelStream(Protocol):
    def generate_stream(
        self, messages: list[Message], model: str, **kwargs: Any
    ) -> AsyncIterator[dict[str, Any]]: ...


class ToolRunner(Protocol):
    def definitions(self) -> list[dict[str, Any]]: ...

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any: ...


class AgentLoopError(RuntimeError):
    """A controlled runtime failure suitable for user-facing rendering."""

    def __init__(self, message: str, *, category: str = "runtime") -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class AgentLoopConfig:
    max_rounds: int = 12
    max_run_seconds: float = 300.0
    emergency_max_tool_calls: int = 128
    max_input_tokens: int = 32_000
    duplicate_reuse_limit: int = 1
    model: str = "reasoning"
    repair_model: str | None = None
    escalation_model: str | None = None
    decision_provider: Any | None = None
    mode: str = "guided"
    max_tokens: int = 8192
    report_max_tokens: int = 32768
    report_repair_max_tokens: int = 8192
    max_report_repairs: int = 2
    report_repair_timeout_seconds: float = 120.0
    publish_reports: bool = False
    allowed_tools: frozenset[str] | None = None
    route_plan: RoutePlan | None = None
    resolved_ticker: str | None = None


class AgentLoop:
    """Run a conversation until the model answers, pauses, or reaches a limit."""

    def __init__(
        self,
        model_client: ModelStream,
        tool_runner: ToolRunner,
        *,
        config: AgentLoopConfig | None = None,
        skill_registry: SkillRegistry | None = None,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self.model_client = model_client
        self.tool_runner = tool_runner
        self.config = config or AgentLoopConfig()
        self.prompt_registry = prompt_registry or PromptRegistry.bundled()
        self.skill_registry = skill_registry

    @observe("workflow.report_generation", as_type="workflow")
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
        history.insert(
            0,
            Message(
                role="system",
                content=self.prompt_registry.get("agent_loop.core.system"),
                prompt_key="agent_loop.core.system",
            ),
        )
        history = _add_skill_context(history, selected_skills, self.prompt_registry)
        if self.config.publish_reports:
            history.append(
                Message(
                    role="system",
                    content=self.prompt_registry.get("agent_loop.report.system"),
                    prompt_key="agent_loop.report.system",
                )
            )
        tool_calls_seen = 0
        invalid_tool_attempts: dict[tuple[str, str], int] = {}
        tool_signature_attempts: dict[str, int] = {}
        successful_tool_signatures: set[str] = set()
        tool_results_by_signature: dict[str, str] = {}
        duplicate_reuses = 0
        tools_disabled = False
        failed_tools = 0
        successful_tools = 0
        evidence = EvidenceAccounting()
        evidence_warning_added = False
        report_parse_repair_attempts = 0
        report_validation_repair_attempts = 0
        model_generation_retry_attempts = 0
        output_review_attempts = 0
        availability_context_snapshot: str | None = None
        controller_route: RoutePlan | None = None
        stop_reason: str | None = None
        tool_executor = ToolExecutor(
            self.tool_runner, self._allowed_tool_names(selected_skills)
        )
        set_current_span_attributes(
            {
                "workflow.name": "report_generation",
                "app.conversation_id": str(conversation_id),
                "app.publish_reports": self.config.publish_reports,
                "app.model": self.config.model,
            }
        )
        completed_tool_ids = {
            message.tool_call_id
            for message in history
            if message.role == "tool" and message.tool_call_id
        }
        for message in history:
            if message.role != "assistant" or not message.tool_calls:
                continue
            for call in message.tool_calls:
                try:
                    name, call_id, arguments = _tool_call_parts(call)
                except AgentLoopError:
                    continue
                if call_id in completed_tool_ids:
                    successful_tool_signatures.add(
                        _tool_call_signature(name, arguments)
                    )
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
        set_current_span_attributes({"app.run_id": str(factory.run_id)})
        yield factory.make(RunStarted, query=_last_user_query(history))
        if self.config.route_plan is not None:
            route = self.config.route_plan
            yield factory.make(
                RouteDecisionMade,
                intent=route.intent,
                execution_mode=route.execution_mode.value,
                model_tier=route.model_tier.value,
                confidence=route.confidence,
                reason_codes=route.reason_codes,
                required_tools=route.required_tools,
                reason=route.reason,
                selected_provider=route.selected_provider,
                selected_model=route.selected_model,
                next_action=route.next_action.value,
                prompt_injection_risk=route.prompt_injection_risk.value,
                risk_flags=route.risk_flags,
                evidence_sufficient=route.evidence_sufficient,
                escalation_reason=route.escalation_reason,
            )
        for skill in selected_skills:
            yield factory.make(
                SkillSelected,
                skill_id=skill.manifest.id,
                version=skill.manifest.version,
                package_hash=skill.sha256,
            )
        yield factory.make(StageStarted, stage="agent", label="Preparing research")
        if self.config.route_plan is not None:
            route = self.config.route_plan
            if route.next_action is NextAction.ASK_CLARIFICATION:
                prompt = _clarification_prompt(route)
                if checkpoint_writer:
                    checkpoint_writer(
                        {
                            "messages": [
                                message.model_dump(mode="json") for message in history
                            ],
                            "tool_name": "interaction:ask_user",
                            "arguments": {"question": prompt},
                            "status": "awaiting_clarification",
                        }
                    )
                yield factory.make(ClarificationRequested, prompt=prompt)
                yield factory.make(
                    RunCompleted,
                    terminal_status="awaiting_clarification",
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                )
                return
            if route.next_action is NextAction.DENY:
                yield factory.make(
                    RunCompleted,
                    terminal_status="denied",
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                )
                return

        try:
            for round_number in range(1, self.config.max_rounds + 1):
                if time.perf_counter() - started >= self.config.max_run_seconds:
                    stop_reason = "run time budget reached"
                    break
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
                stream_error: Exception | None = None
                resumed_assistant = None
                if assistant is None:
                    if self.config.publish_reports and evidence.availability:
                        availability_snapshot = json.dumps(
                            {
                                "available": [
                                    key
                                    for key, value in evidence.availability.items()
                                    if value["status"] == "available"
                                ],
                                "missing": [
                                    value
                                    for value in evidence.availability.values()
                                    if value["status"] in {"unavailable", "degraded"}
                                ],
                            },
                            sort_keys=True,
                        )
                    else:
                        availability_snapshot = None
                    if (
                        self.config.publish_reports
                        and evidence.availability
                        and availability_snapshot != availability_context_snapshot
                    ):
                        assert availability_snapshot is not None
                        availability_context_snapshot = availability_snapshot
                        history.append(
                            Message(
                                role="system",
                                content=self.prompt_registry.render(
                                    "agent_loop.report.availability",
                                    availability_snapshot=availability_snapshot,
                                ),
                                prompt_key="agent_loop.report.availability",
                            )
                        )
                    yield factory.make(
                        ModelRequestStarted,
                        model=self._model_for_history(history, controller_route),
                        round=round_number,
                    )
                    streamed_text: list[str] = []
                    provider_stream_started = False
                    try:
                        async for item in self._stream_model(
                            history,
                            factory,
                            round_number,
                            selected_skills,
                            controller_route,
                            disable_tools=tools_disabled,
                        ):
                            if isinstance(item, TextDelta):
                                streamed_text.append(item.text)
                                if not self.config.publish_reports:
                                    yield item
                            elif isinstance(
                                item,
                                (
                                    ProviderAttemptStarted,
                                    ProviderRetrying,
                                    ProviderCompleted,
                                    ProviderFailed,
                                ),
                            ):
                                yield item
                            elif isinstance(item, ProviderStreamStarted):
                                provider_stream_started = True
                                yield item
                            else:
                                assistant = item
                        controller_route = None
                    except Exception as exc:
                        stream_error = exc
                        partial_text = "".join(streamed_text)
                        set_current_span_attributes(
                            {
                                "provider.error_type": type(exc).__name__,
                                "provider.partial_output": bool(partial_text),
                                "provider.partial_output_chars": len(partial_text),
                            }
                        )
                        if (
                            len(partial_text.strip()) < _PARTIAL_RESPONSE_MIN_CHARS
                            and not (provider_stream_started and evidence.facts)
                            and not self.config.publish_reports
                        ):
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
                    if assistant is None and self.config.publish_reports:
                        assistant = Message(
                            role="assistant",
                            name="partial_provider_response",
                            content="",
                        )
                    if assistant is None:
                        raise AgentLoopError("model stream ended without a response")
                    if not assistant.tool_calls and not assistant.content.strip():
                        if (
                            not self.config.publish_reports
                            and model_generation_retry_attempts < 1
                        ):
                            model_generation_retry_attempts += 1
                            history.append(
                                Message(
                                    role="system",
                                    content=self.prompt_registry.get("agent_loop.retry.empty_answer"),
                                    prompt_key="agent_loop.retry.empty_answer",
                                )
                            )
                            continue
                        raise AgentLoopError(
                            "model generation returned empty content",
                            category="model_generation",
                        )
                    if assistant.tool_calls:
                        assistant, ticker_resolved = _hydrate_tool_call_tickers(
                            assistant, self.config.resolved_ticker
                        )
                        if not ticker_resolved:
                            question = self.prompt_registry.get(
                                "agent_loop.clarification.ticker"
                            )
                            if checkpoint_writer:
                                checkpoint_writer(
                                    {
                                        "messages": [
                                            message.model_dump(mode="json")
                                            for message in history
                                        ],
                                        "tool_name": "interaction:ask_user",
                                        "arguments": {"question": question},
                                        "status": "awaiting_clarification",
                                    }
                                )
                            yield factory.make(ClarificationRequested, prompt=question)
                            return
                    history.append(assistant)
                    if (
                        not assistant.tool_calls
                        and not self.config.publish_reports
                        and self.config.decision_provider
                        and hasattr(self.config.decision_provider, "review_output")
                    ):
                        review = await self.config.decision_provider.review_output(
                            _output_review_context(history, assistant.content)
                        )
                        if review is NextAction.DENY:
                            raise AgentLoopError(
                                "generated output failed safety review",
                                category="output_policy",
                            )
                        if (
                            review
                            in {NextAction.REPAIR_OUTPUT, NextAction.ESCALATE_MODEL}
                            and output_review_attempts < 1
                        ):
                            output_review_attempts += 1
                            history.append(
                                Message(
                                    role="system",
                                    content=self.prompt_registry.get("agent_loop.retry.output_review"),
                                    prompt_key="agent_loop.retry.output_review",
                                )
                            )
                            controller_route = RoutePlan(
                                intent="output_review",
                                execution_mode=ExecutionMode.REPAIR,
                                model_tier=ModelTier.MAIN,
                                next_action=review,
                                confidence=1.0,
                                reason="Jev requested bounded output review.",
                            )
                            continue
                    if message_writer and (
                        not self.config.publish_reports or assistant.tool_calls
                    ):
                        message_writer(assistant)
                    yield factory.make(
                        ModelResponseCompleted,
                        round=round_number,
                        has_tool_calls=bool(assistant.tool_calls),
                    )

                if not assistant.tool_calls:
                    partial_provider_response = (
                        assistant.name == "partial_provider_response"
                        and bool(assistant.content.strip())
                    )
                    status = terminal_status(
                        failed_tools=failed_tools,
                        successful_tools=successful_tools,
                        requires_evidence=(
                            (
                                self.config.publish_reports
                                and not partial_provider_response
                            )
                            or _requires_evidence(selected_skills)
                        ),
                        successful_evidence_tools=evidence.successful_evidence_tools,
                        invalid_evidence=evidence.invalid_evidence,
                        partial_provider_response=partial_provider_response,
                    )
                    if (
                        self.config.publish_reports
                        and not evidence.facts
                        and not partial_provider_response
                    ):
                        published = report_validation_fallback(
                            evidence.facts,
                            ("evidence_unavailable",),
                            availability=evidence.availability,
                        )
                        if message_writer:
                            message_writer(Message(role="assistant", content=published))
                        for offset in range(0, len(published), 64):
                            yield factory.make(
                                TextDelta, text=published[offset : offset + 64]
                            )
                        yield factory.make(
                            RunCompleted,
                            terminal_status="completed_with_limited_evidence",
                            duration_ms=round(
                                (time.perf_counter() - started) * 1000, 2
                            ),
                            evidence_status="limited",
                            evidence_availability=list(evidence.availability.values()),
                        )
                        return
                    if self.config.publish_reports:
                        if not assistant.content.strip():
                            if model_generation_retry_attempts < 1:
                                model_generation_retry_attempts += 1
                                history.append(
                                    Message(
                                        role="system",
                                        content=self.prompt_registry.get("agent_loop.retry.empty_report"),
                                        prompt_key="agent_loop.retry.empty_report",
                                    )
                                )
                                continue
                            raise AgentLoopError(
                                "model generation returned empty report",
                                category="model_generation",
                            )
                        try:
                            published = publish_report(
                                parse_report_draft(assistant.content),
                                evidence.facts,
                                evidence.sources,
                                evidence.availability,
                            )
                            status = (
                                "completed_with_limited_evidence"
                                if evidence.availability
                                and any(
                                    item["status"] in {"unavailable", "degraded"}
                                    for item in evidence.availability.values()
                                )
                                or partial_provider_response
                                else "completed"
                            )
                        except ReportParseError as exc:
                            logger.warning(
                                "report parsing failed run_id=%s error=%s",
                                factory.run_id,
                                exc.detail,
                            )
                            if (
                                report_parse_repair_attempts
                                + report_validation_repair_attempts
                                < self.config.max_report_repairs
                            ):
                                report_parse_repair_attempts += 1
                                with span(
                                    "report.repair",
                                    {
                                        "repair.reason": "parse_failure",
                                        "report.parse_error": exc.detail,
                                        "repair.attempt": report_parse_repair_attempts,
                                    },
                                ) as repair_span:
                                    repair_span.add_event(
                                        "repair.requested", {"error": exc.detail}
                                    )
                                    history.append(
                                        Message(
                                            role="system",
                                            content=report_repair_instruction(
                                                evidence.facts,
                                                exc.reasons,
                                                parse_error=exc.detail,
                                                sources=evidence.sources,
                                                prompts=self.prompt_registry,
                                            ),
                                            prompt_key="publication.report_repair",
                                        )
                                    )
                                continue
                            if evidence.facts:
                                published = report_validation_fallback(
                                    evidence.facts,
                                    (*exc.reasons, "runtime_failure"),
                                )
                                status = "completed_with_limited_evidence"
                                set_current_span_attributes(
                                    {
                                        "fallback.used": True,
                                        "fallback.reason": "report_parse_repair_failure",
                                    }
                                )
                                logger.error(
                                    "using evidence fallback after report repair failure "
                                    "run_id=%s stream_error=%s parse_error=%s",
                                    factory.run_id,
                                    type(stream_error).__name__
                                    if stream_error
                                    else None,
                                    exc.detail,
                                )
                            else:
                                raise AgentLoopError(
                                    f"report parsing failed after repair: {exc.detail}",
                                    category="report_parse",
                                ) from exc
                        except PublicationError as exc:
                            logger.warning(
                                "report publication validation failed run_id=%s reasons=%s",
                                factory.run_id,
                                exc.reasons,
                            )
                            if (
                                report_parse_repair_attempts
                                + report_validation_repair_attempts
                                < self.config.max_report_repairs
                            ):
                                report_validation_repair_attempts += 1
                                with span(
                                    "report.repair",
                                    {
                                        "repair.reason": "publication_validation_failure",
                                        "report.validation_error": str(exc),
                                        "repair.attempt": report_validation_repair_attempts,
                                    },
                                ):
                                    history.append(
                                        Message(
                                            role="system",
                                            content=report_repair_instruction(
                                                evidence.facts,
                                                exc.reasons,
                                                sources=evidence.sources,
                                                prompts=self.prompt_registry,
                                            ),
                                            prompt_key="publication.report_repair",
                                        )
                                    )
                                continue
                            if evidence.facts:
                                published = report_validation_fallback(
                                    evidence.facts,
                                    (*exc.reasons, "runtime_failure"),
                                )
                                status = "completed_with_limited_evidence"
                                set_current_span_attributes(
                                    {
                                        "fallback.used": True,
                                        "fallback.reason": "publication_repair_failure",
                                    }
                                )
                                logger.error(
                                    "using evidence fallback after publication repair failure "
                                    "run_id=%s stream_error=%s reasons=%s",
                                    factory.run_id,
                                    type(stream_error).__name__
                                    if stream_error
                                    else None,
                                    exc.reasons,
                                )
                            else:
                                raise AgentLoopError(
                                    "report publication validation failed after repair: "
                                    + "; ".join(exc.reasons),
                                    category="report_validation",
                                ) from exc
                        if message_writer:
                            message_writer(Message(role="assistant", content=published))
                        for offset in range(0, len(published), 64):
                            yield factory.make(
                                TextDelta, text=published[offset : offset + 64]
                            )
                    yield factory.make(
                        RunCompleted,
                        terminal_status=status,
                        duration_ms=round((time.perf_counter() - started) * 1000, 2),
                        evidence_status=(
                            "limited"
                            if any(
                                item["status"] in {"unavailable", "degraded"}
                                for item in evidence.availability.values()
                            )
                            else "complete"
                        ),
                        evidence_availability=list(evidence.availability.values()),
                    )
                    return

                for call in assistant.tool_calls:
                    tool_calls_seen += 1
                    if tool_calls_seen > self.config.emergency_max_tool_calls:
                        stop_reason = "emergency tool-call safety ceiling reached"
                        break
                    try:
                        name, call_id, arguments = _tool_call_parts(call)
                    except AgentLoopError as exc:
                        name, call_id = _tool_call_identity(call)
                        message = str(exc)
                        invalid_key = (name, message)
                        invalid_tool_attempts[invalid_key] = (
                            invalid_tool_attempts.get(invalid_key, 0) + 1
                        )
                        if invalid_tool_attempts[invalid_key] > 1:
                            raise AgentLoopError(
                                f"repeated invalid tool call: {message}",
                                category="tool_validation",
                            ) from exc
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
                                content=json.dumps(
                                    {"success": False, "error": message}
                                ),
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
                    signature = _tool_call_signature(name, arguments)
                    if (
                        signature in successful_tool_signatures
                        or tool_signature_attempts.get(signature, 0) >= 1
                    ):
                        cached = tool_results_by_signature.get(signature)
                        if (
                            cached is not None
                            and duplicate_reuses < self.config.duplicate_reuse_limit
                        ):
                            duplicate_reuses += 1
                            history.append(
                                Message(
                                    role="tool",
                                    content=cached,
                                    tool_call_id=call_id,
                                )
                            )
                            if message_writer:
                                message_writer(history[-1])
                            yield factory.make(
                                ToolCompleted,
                                tool=name,
                                tool_id=call_id,
                                detail="reused cached evidence",
                                duration_ms=0.0,
                            )
                            continue
                        tools_disabled = True
                        history.append(
                            Message(
                                role="system",
                                content=self.prompt_registry.render(
                                    "agent_loop.tool.duplicate_request", tool_name=name
                                ),
                                prompt_key="agent_loop.tool.duplicate_request",
                            )
                        )
                        break
                    tool_signature_attempts[signature] = (
                        tool_signature_attempts.get(signature, 0) + 1
                    )
                    if name == "interaction:ask_user":
                        question = str(
                            arguments.get("question", "Please clarify the request.")
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
                                    "arguments": arguments,
                                    "status": "awaiting_clarification",
                                }
                            )
                        yield factory.make(ClarificationRequested, prompt=question)
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
                        payload = await tool_executor.execute(name, arguments)
                    except asyncio.CancelledError:
                        yield factory.make(RunCancelled, reason="cancelled by user")
                        return
                    if diagnostics_enabled():
                        logger.debug(
                            "tool call end run_id=%s tool=%s tool_id=%s duration_ms=%.1f success=%s",
                            factory.run_id,
                            name,
                            call_id,
                            (time.perf_counter() - tool_started) * 1000,
                            payload.get("success", True),
                        )

                    tool_content = _tool_message_content(payload)
                    tool_results_by_signature[signature] = tool_content
                    content_safety = assess_input_safety(tool_content)
                    if content_safety.risk.value == "high":
                        history.append(
                            Message(
                                role="system",
                                content=self.prompt_registry.get("agent_loop.tool.untrusted_content"),
                                prompt_key="agent_loop.tool.untrusted_content",
                            )
                        )

                    if payload.get("success", True) is False:
                        if not payload.get("retryable", False):
                            failed_tools += 1
                        evidence.record_failure(name, payload)
                        message = str(
                            redact_secrets(payload.get("error", "tool failed"))
                        )
                        if payload.get("retryable", False):
                            invalid_key = (name, message)
                            invalid_tool_attempts[invalid_key] = (
                                invalid_tool_attempts.get(invalid_key, 0) + 1
                            )
                            if invalid_tool_attempts[invalid_key] > 1:
                                raise AgentLoopError(
                                    f"repeated invalid tool call: {message}",
                                    category="tool_validation",
                                )
                        if (
                            name in _EVIDENCE_TOOLS
                            and not payload.get("retryable", False)
                            and not evidence_warning_added
                        ):
                            history.append(
                                Message(
                                    role="system",
                                    content=self.prompt_registry.get("agent_loop.tool.evidence_failure"),
                                    prompt_key="agent_loop.tool.evidence_failure",
                                )
                            )
                            evidence_warning_added = True
                            if message_writer:
                                message_writer(history[-1])
                        if self.config.publish_reports and name in _EVIDENCE_TOOLS:
                            history.append(
                                Message(
                                    role="system",
                                    content=self.prompt_registry.render(
                                        "agent_loop.report.evidence_failure_availability",
                                        availability_json=json.dumps(
                                            evidence.availability, sort_keys=True
                                        ),
                                    ),
                                    prompt_key="agent_loop.report.evidence_failure_availability",
                                )
                            )
                            if message_writer:
                                message_writer(history[-1])
                        history.append(
                            Message(
                                role="tool",
                                content=tool_content,
                                tool_call_id=call_id,
                            )
                        )
                        if message_writer:
                            message_writer(history[-1])
                        if payload.get("retryable", False):
                            history.append(
                                Message(
                                    role="system",
                                    content=self.prompt_registry.get("agent_loop.tool.invalid_arguments"),
                                    prompt_key="agent_loop.tool.invalid_arguments",
                                )
                            )
                        yield factory.make(
                            ToolFailed, tool=name, tool_id=call_id, message=message
                        )
                    else:
                        successful_tools += 1
                        successful_tool_signatures.add(signature)
                        evidence.record_success(name, payload)
                        history.append(
                            Message(
                                role="tool",
                                content=tool_content,
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
                            duration_ms=round(
                                (time.perf_counter() - tool_started) * 1000, 2
                            ),
                        )
                        sources = _extract_sources(payload)
                        if sources:
                            yield factory.make(SourcesUpdated, sources=sources)
                    self._drain_input_queue(history, input_queue)
                if stop_reason:
                    for event in _limited_completion(
                        factory, started, stop_reason, evidence
                    ):
                        yield event
                    return
                if (
                    self.config.publish_reports
                    and not evidence.facts
                    and any(
                        item["status"] in {"unavailable", "degraded"}
                        for item in evidence.availability.values()
                    )
                ):
                    published = report_validation_fallback(
                        evidence.facts,
                        availability=evidence.availability,
                    )
                    if message_writer:
                        message_writer(Message(role="assistant", content=published))
                    for offset in range(0, len(published), 64):
                        yield factory.make(
                            TextDelta, text=published[offset : offset + 64]
                        )
                    yield factory.make(
                        RunCompleted,
                        terminal_status="completed_with_limited_evidence",
                        duration_ms=round((time.perf_counter() - started) * 1000, 2),
                        evidence_status="limited",
                        evidence_availability=list(evidence.availability.values()),
                    )
                    return
                if (
                    self.config.decision_provider
                    and tool_calls_seen
                    and not tools_disabled
                ):
                    try:
                        controller_route = await self.config.decision_provider.decide(
                            _controller_context(
                                history,
                                evidence,
                                self._allowed_tool_names(selected_skills),
                            )
                        )
                        yield factory.make(
                            RouteDecisionMade,
                            intent=controller_route.intent,
                            execution_mode=controller_route.execution_mode.value,
                            model_tier=controller_route.model_tier.value,
                            confidence=controller_route.confidence,
                            reason_codes=[
                                *controller_route.reason_codes,
                                "evidence_review_checkpoint",
                            ],
                            required_tools=controller_route.required_tools,
                            reason=controller_route.reason,
                            selected_provider=controller_route.selected_provider,
                            selected_model=controller_route.selected_model,
                            next_action=controller_route.next_action.value,
                            prompt_injection_risk=controller_route.prompt_injection_risk.value,
                            risk_flags=controller_route.risk_flags,
                            evidence_sufficient=controller_route.evidence_sufficient,
                            escalation_reason=controller_route.escalation_reason,
                        )
                    except Exception:  # noqa: BLE001 - checkpoint is advisory and bounded
                        controller_route = None
                    if controller_route is not None:
                        if controller_route.next_action is NextAction.ASK_CLARIFICATION:
                            prompt = _clarification_prompt(controller_route)
                            if checkpoint_writer:
                                checkpoint_writer(
                                    {
                                        "messages": [
                                            message.model_dump(mode="json")
                                            for message in history
                                        ],
                                        "tool_name": "interaction:ask_user",
                                        "arguments": {"question": prompt},
                                        "status": "awaiting_clarification",
                                    }
                                )
                            yield factory.make(ClarificationRequested, prompt=prompt)
                            yield factory.make(
                                RunCompleted,
                                terminal_status="awaiting_clarification",
                                duration_ms=round(
                                    (time.perf_counter() - started) * 1000, 2
                                ),
                            )
                            return
                        if controller_route.next_action is NextAction.DENY:
                            yield factory.make(
                                RunCompleted,
                                terminal_status="denied",
                                duration_ms=round(
                                    (time.perf_counter() - started) * 1000, 2
                                ),
                            )
                            return
                if (
                    not self.config.publish_reports
                    and evidence.failed_evidence_tools
                    and not evidence.successful_evidence_tools
                ):
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
            if self.config.max_rounds == 0:
                raise AgentLoopError("agent round limit reached for this run")
            for event in _limited_completion(
                factory, started, "model round limit reached", evidence
            ):
                yield event
        except asyncio.CancelledError:
            yield factory.make(RunCancelled, reason="cancelled by user")
        except Exception as exc:
            logger.exception("Agent loop failed")
            yield factory.make(
                RunFailed,
                message=str(exc),
                category=getattr(exc, "category", "runtime"),
            )

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
            "analysis:run_fundamental_scan",
            "analysis:run_technical_scan",
            "analysis:get_technical_overview",
            "interaction:ask_user",
        }
        if not skills:
            allowed: set[str] | None = None
        else:
            allowed = {
                tool for skill in skills for tool in skill.manifest.allowed_tools
            }
            if not allowed:
                allowed = base_tools
        if self.config.allowed_tools is not None:
            if allowed is None:
                allowed = {
                    str(definition.get("function", {}).get("name", ""))
                    for definition in definitions
                }
            allowed &= set(self.config.allowed_tools)
        if allowed is None:
            return definitions
        return [
            definition
            for definition in definitions
            if definition.get("function", {}).get("name") in allowed
        ]

    def _allowed_tool_names(self, skills: list[SkillPackage]) -> set[str]:
        return {
            str(definition.get("function", {}).get("name"))
            for definition in self._tool_definitions(skills)
        }

    async def _stream_model(
        self,
        messages: list[Message],
        factory: EventFactory,
        round_number: int,
        skills: list[SkillPackage],
        controller_route: RoutePlan | None = None,
        disable_tools: bool = False,
    ) -> AsyncIterator[
        TextDelta
        | Message
        | ProviderAttemptStarted
        | ProviderRetrying
        | ProviderStreamStarted
        | ProviderCompleted
        | ProviderFailed
    ]:
        is_repair = any(
            message.prompt_key == "publication.report_repair"
            for message in messages
        )
        streamer = ModelStreaming(
            self.model_client,
            self._model_for_history(messages, controller_route),
            self.config.max_tokens,
            lambda: (
                []
                if disable_tools
                else self._controller_tools(skills, controller_route, is_repair)
            ),
            publish_reports=self.config.publish_reports,
            report_max_tokens=self.config.report_max_tokens,
            report_repair_max_tokens=self.config.report_repair_max_tokens,
            report_repair_timeout_seconds=self.config.report_repair_timeout_seconds,
        )
        request_messages = _report_repair_history(messages) if is_repair else messages
        request_messages = _compact_model_history(
            request_messages, self.config.max_input_tokens
        )
        async for item in streamer.stream(request_messages, factory, round_number):
            yield item

    def _model_for_history(
        self, messages: list[Message], controller_route: RoutePlan | None = None
    ) -> str:
        if controller_route is not None:
            if (
                controller_route.next_action.value == "escalate_model"
                and self.config.escalation_model
            ):
                return self.config.escalation_model
            if (
                controller_route.next_action.value == "repair_output"
                and self.config.repair_model
            ):
                return self.config.repair_model
        repair_attempts = sum(
            message.prompt_key == "publication.report_repair"
            for message in messages
        )
        if self.config.publish_reports and repair_attempts >= 1:
            return self.config.repair_model or self.config.model
        if repair_attempts >= 2 and self.config.escalation_model:
            return self.config.escalation_model
        if repair_attempts == 1 and self.config.repair_model:
            return self.config.repair_model
        return self.config.model

    def _controller_tools(
        self,
        skills: list[SkillPackage],
        route: RoutePlan | None,
        is_repair: bool,
    ) -> list[dict[str, Any]]:
        if is_repair or route is None:
            return [] if is_repair else self._tool_definitions(skills)
        if route.next_action.value in {
            "generate_text",
            "repair_output",
            "escalate_model",
            "finish_with_limitations",
        }:
            return []
        definitions = self._tool_definitions(skills)
        if not route.required_tools:
            return definitions
        return [
            definition
            for definition in definitions
            if definition.get("function", {}).get("name") in route.required_tools
        ]

    @staticmethod
    def _drain_input_queue(
        history: list[Message], queue: asyncio.Queue[Message] | None
    ) -> None:
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


def _tool_call_signature(name: str, arguments: dict[str, Any]) -> str:
    return f"{name}:{json.dumps(_normalize_tool_arguments(arguments), sort_keys=True)}"


def _normalize_tool_arguments(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalize_tool_arguments(item) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalize_tool_arguments(item) for item in value]
    if isinstance(value, str):
        return " ".join(value.split()).upper()
    return value


def _compact_model_history(messages: list[Message], max_tokens: int) -> list[Message]:
    """Bound provider input while retaining the user request and newest evidence."""
    compacted = list(messages)
    for index, message in enumerate(compacted):
        if message.role == "tool" and len(message.content) > 6_000:
            compacted[index] = message.model_copy(
                update={
                    "content": message.content[:6_000]
                    + "\n[tool output truncated for model context budget]"
                }
            )
    while _estimate_message_tokens(compacted) > max_tokens:
        removable = next(
            (
                index
                for index, message in enumerate(compacted)
                if message.role == "tool"
            ),
            None,
        )
        if removable is None:
            break
        compacted.pop(removable)
    return compacted


def _estimate_message_tokens(messages: list[Message]) -> int:
    return sum((len(message.content) + 3) // 4 for message in messages) + sum(
        (len(json.dumps(message.tool_calls, sort_keys=True)) + 3) // 4
        for message in messages
        if message.tool_calls
    )


def _limited_completion(
    factory: EventFactory,
    started: float,
    reason: str,
    evidence: EvidenceAccounting,
) -> list[ResearchEvent]:
    message = (
        "I stopped this run safely because it reached a runtime boundary: "
        f"{reason}. I kept the evidence collected so far and will not repeat the same request."
    )
    return [
        factory.make(TextDelta, text=message),
        factory.make(
            RunCompleted,
            terminal_status="completed_with_limits",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            completion_reason=reason,
            evidence_status=(
                "limited"
                if any(
                    item["status"] in {"unavailable", "degraded"}
                    for item in evidence.availability.values()
                )
                else "complete"
            ),
            evidence_availability=list(evidence.availability.values()),
        ),
    ]


def _hydrate_tool_call_tickers(
    assistant: Message, resolved_ticker: str | None = None
) -> tuple[Message, bool]:
    """Fill missing research tickers from validated context or sibling calls."""
    tool_calls = assistant.tool_calls or []
    parsed: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    explicit_tickers: set[str] = set()
    missing_ticker = False
    for call in tool_calls:
        try:
            name, _, arguments = _tool_call_parts(call)
        except AgentLoopError:
            return assistant, True
        parsed.append((call, name, arguments))
        if name not in _TICKER_TOOLS:
            continue
        ticker = arguments.get("ticker")
        if not isinstance(ticker, str) or not ticker.strip():
            missing_ticker = True
            continue
        try:
            explicit_tickers.add(parse_ticker(ticker).provider_symbol)
        except ValueError:
            missing_ticker = True
    if not missing_ticker:
        return assistant, True
    if resolved_ticker:
        try:
            context_ticker = parse_ticker(resolved_ticker).provider_symbol
        except ValueError:
            context_ticker = None
        if context_ticker:
            if explicit_tickers and explicit_tickers != {context_ticker}:
                return assistant, False
            context_hydrated_calls: list[dict[str, Any]] = []
            for call, name, arguments in parsed:
                value = dict(call)
                function = dict(value.get("function") or {})
                if name in _TICKER_TOOLS and not arguments.get("ticker"):
                    function["arguments"] = json.dumps(
                        {**arguments, "ticker": context_ticker}
                    )
                    value["function"] = function
                context_hydrated_calls.append(value)
            return assistant.model_copy(update={"tool_calls": context_hydrated_calls}), True
    if len(explicit_tickers) != 1:
        return assistant, False
    ticker = explicit_tickers.pop()
    hydrated_calls: list[dict[str, Any]] = []
    for call, name, arguments in parsed:
        value = dict(call)
        function = dict(value.get("function") or {})
        if name in _TICKER_TOOLS and not arguments.get("ticker"):
            function["arguments"] = json.dumps({**arguments, "ticker": ticker})
            value["function"] = function
        hydrated_calls.append(value)
    return assistant.model_copy(update={"tool_calls": hydrated_calls}), True


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


def _tool_message_content(payload: dict[str, Any], *, max_chars: int = 7_500) -> str:
    """Bound provider results before inserting them into model history."""
    encoded = json.dumps(payload, default=str)
    if len(encoded) <= max_chars:
        return encoded
    compact = {
        "success": payload.get("success", True),
        "truncated": True,
        "summary": _summary(payload),
        "provenance": payload.get("provenance"),
    }
    error = payload.get("error")
    if error:
        compact["error"] = error
    return json.dumps(compact, default=str)


def _extract_sources(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Extract a small, presentation-safe source list from tool evidence."""
    candidates: Any = payload.get("sources")
    if candidates is None and isinstance(payload.get("provenance"), dict):
        source = payload["provenance"].get("source")
        if source:
            candidates = [
                {
                    "name": source,
                    "url": payload["provenance"].get("source_url", ""),
                }
            ]
    if candidates is None and isinstance(payload.get("data"), dict):
        candidates = payload["data"].get("sources")
    if not isinstance(candidates, list):
        candidates = (
            payload.get("data") if isinstance(payload.get("data"), list) else []
        )

    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        name = str(
            item.get("name") or item.get("publisher") or item.get("source") or ""
        ).strip()
        url = str(item.get("url") or item.get("link") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        sources.append({"name": name, "url": url})
    return sources


def _requires_evidence(skills: list[SkillPackage]) -> bool:
    """Return whether the selected workflow may publish without evidence."""
    return any(skill.manifest.id in _EVIDENCE_REQUIRED_SKILLS for skill in skills)


def _controller_context(
    history: list[Message],
    evidence: EvidenceAccounting,
    available_tools: set[str],
) -> dict[str, Any]:
    """Build bounded post-tool state for one Jev control checkpoint."""
    failures = [
        {
            "source": key,
            "status": value.get("status"),
            "reason": str(value.get("reason") or "")[:160],
        }
        for key, value in evidence.availability.items()
        if value.get("status") in {"unavailable", "degraded"}
    ]
    return {
        "query": _last_user_query(history),
        "normalized_query": _last_user_query(history),
        "available_tools": sorted(available_tools),
        "available_skills": [],
        "evidence_status": evidence.availability,
        "prior_failures": failures[-8:],
        "provider_health": {},
        "phase": "evidence_review",
        "evidence_sufficient": bool(evidence.facts),
    }


def _output_review_context(history: list[Message], output: str) -> dict[str, Any]:
    return {
        "query": _last_user_query(history),
        "normalized_query": _last_user_query(history),
        "available_tools": [],
        "available_skills": [],
        "evidence_status": {},
        "prior_failures": [],
        "provider_health": {},
        "phase": "output_review",
        "output": str(redact_secrets(output))[:4000],
    }


def _last_user_query(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def _add_skill_context(
    messages: list[Message], skills: list[SkillPackage], prompts: PromptRegistry
) -> list[Message]:
    if not skills:
        return messages
    skill_text = "\n\n---\n\n".join(skill.prompt(prompts) for skill in skills)
    if messages and messages[0].prompt_key == "agent_loop.core.system":
        messages[0] = messages[0].model_copy(
            update={"content": f"{messages[0].content}\n\n{skill_text}"}
        )
        return messages
    return [
        Message(role="system", content=skill_text, prompt_key="skills.selected"),
        *messages,
    ]
