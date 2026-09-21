"""Production research runner used by the terminal session facade."""

from __future__ import annotations

import json
import re
import time
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID

from app.config import settings
from app.core.agent_loop import AgentLoop, AgentLoopConfig, FinancialToolRunner
from app.core.instrument_resolution import InstrumentResolution, resolve_instrument
from app.core.prompts import PromptRegistry
from app.core.query_scope import normalize_research_scope
from app.core.resources import RuntimeResources
from app.core.skills import SkillRegistry
from app.events.models import (
    ClarificationRequested,
    EventFactory,
    ResearchEvent,
    RouteDecisionMade,
    RunCompleted,
    RunStarted,
    StageStarted,
    TextDelta,
    ToolCompleted,
    ToolFailed,
    ToolStarted,
)
from app.models.request_models import Message
from app.models.routing import ExecutionMode, ModelTier, NextAction, RoutePlan
from finai.context_budget import build_router_context


def _wants_report(query: str) -> bool:
    lowered = query.casefold().strip()
    for prefix in (
        "i want you to ",
        "i'd like you to ",
        "i would like you to ",
        "please ",
        "can you ",
        "could you ",
        "would you ",
        "help me ",
    ):
        if lowered.startswith(prefix):
            lowered = lowered[len(prefix) :].lstrip()
            break
    return lowered.startswith(
        ("analyze ", "analyse ", "analsye ", "research ", "compare ")
    ) or any(
        marker in lowered
        for marker in (
            "report",
            "investment thesis",
            "full analysis",
            "detailed analysis",
        )
    )


class ResearchRunner:
    """Construct and run one bounded AgentLoop with explicit dependencies."""

    def __init__(self, resources: RuntimeResources, mode: str) -> None:
        self.resources = resources
        self.model_service = resources.llm_service
        self.routing_policy = resources.routing_policy
        self.mode = mode
        self.tool_runner = FinancialToolRunner(resources)
        self._resolved_tickers: dict[UUID, str] = {}

    async def stream(
        self,
        history: list[Message],
        query: str,
        conversation_id: UUID,
        *,
        mocked_tools: list[dict[str, Any]] | None = None,
        approved_tool_ids: set[str] | None = None,
        checkpoint_writer: Callable[[dict[str, Any]], None] | None = None,
        message_writer: Callable[[Message], None] | None = None,
    ) -> AsyncIterator[ResearchEvent]:
        """Yield events for ``query`` while keeping construction out of the session."""
        self.tool_runner.set_mocked_tools(mocked_tools or [])
        route = None
        resolution, resolution_source = self._resolve_instrument_context(
            history, query, conversation_id
        )
        if resolution.status == "resolved" and resolution.ticker:
            self._resolved_tickers[conversation_id] = resolution.ticker
        conversation_context = build_router_context(
            history,
            query,
            resolved_ticker=resolution.ticker,
            instrument_resolution_status=resolution.status,
            instrument_resolution_source=resolution_source,
            instrument_candidates=list(resolution.candidates),
        )
        if self.routing_policy is not None:
            selected_skills = (self.resources.skills or SkillRegistry.bundled()).select(query)
            route = await self.routing_policy.decide(
                query,
                available_tools={
                    str(item.get("function", {}).get("name"))
                    for item in self.tool_runner.definitions()
                },
                available_skills={skill.manifest.id for skill in selected_skills},
                conversation_context=conversation_context,
            )
        model_service = self.model_service
        selected_provider = (
            "chatgpt_codex"
            if settings.FINAI_CHATGPT_CODEX_ENABLED
            and settings.FINAI_CHATGPT_CODEX_PRIMARY
            else "hive"
        )
        if route is not None and route.model_tier in {
            ModelTier.SMALL,
            ModelTier.MAIN,
        }:
            selected_model = _model_for_route(route, selected_provider)
            route = route.model_copy(
                update={
                    "selected_provider": selected_provider,
                    "selected_model": selected_model,
                }
            )
        if (
            route is not None
            and route.next_action is NextAction.ASK_CLARIFICATION
            and resolution.status == "resolved"
            and _route_requests_instrument_clarification(route)
        ):
            route = route.model_copy(
                update={
                    "intent": "research_report"
                    if _wants_report(normalize_research_scope(query))
                    else "general_question",
                    "execution_mode": (
                        ExecutionMode.REPORT_SYNTHESIS
                        if _wants_report(normalize_research_scope(query))
                        else ExecutionMode.MODEL_ANSWER
                    ),
                    "next_action": NextAction.GENERATE_TEXT,
                    "required_tools": [],
                    "allowed_tools": {
                        str(item.get("function", {}).get("name"))
                        for item in self.tool_runner.definitions()
                    },
                    "reason_codes": [
                        *route.reason_codes,
                        "resolved_instrument_override",
                    ],
                    "reason": "Resolved instrument context satisfies the identity clarification.",
                }
            )
        if (
            resolution.status in {"ambiguous", "unresolved"}
            and _has_instrument_reference(query)
            and (route is None or route.execution_mode is not ExecutionMode.DENY)
        ):
            if route is None:
                route = RoutePlan(
                    intent="clarification",
                    execution_mode=ExecutionMode.DETERMINISTIC,
                    model_tier=ModelTier.NONE,
                    next_action=NextAction.ASK_CLARIFICATION,
                    confidence=1.0,
                    reason=resolution.reason or "Instrument identity is unresolved.",
                )
            clarification = route.model_copy(
                update={
                    "execution_mode": ExecutionMode.DETERMINISTIC,
                    "next_action": NextAction.ASK_CLARIFICATION,
                    "reason": resolution.reason or "Instrument identity is unresolved.",
                    "required_tools": [],
                    "allowed_tools": set(),
                }
            )
            async for event in _run_clarification_route(
                clarification, query, conversation_id, history, checkpoint_writer
            ):
                yield event
            return
        if route is not None and route.execution_mode is ExecutionMode.TOOL_ONLY:
            direct_arguments = _direct_tool_arguments(route, query)
            if (
                direct_arguments is not None
                and route.required_tools[0]
                not in {"data:fetch_market_status", "data:fetch_market_holidays"}
            ):
                if resolution.status in {"ambiguous", "unresolved"}:
                    clarification = route.model_copy(
                        update={
                            "execution_mode": ExecutionMode.DETERMINISTIC,
                            "next_action": NextAction.ASK_CLARIFICATION,
                            "reason": resolution.reason or "Instrument identity is ambiguous.",
                            "required_tools": [],
                            "allowed_tools": set(),
                        }
                    )
                    async for event in _run_clarification_route(
                        clarification, query, conversation_id, history, checkpoint_writer
                    ):
                        yield event
                    return
                if resolution.status == "resolved" and resolution.ticker:
                    direct_arguments = {"ticker": resolution.ticker}
            if direct_arguments is not None:
                async for event in _run_direct_tool(
                    self.tool_runner,
                    route.required_tools[0],
                    direct_arguments,
                    query,
                    conversation_id,
                    route,
                    message_writer,
                ):
                    yield event
                return
        if route is not None and route.execution_mode is ExecutionMode.DENY:
            async for event in _run_denied_route(route, query, conversation_id):
                yield event
            return
        if route is not None and route.next_action.value == "ask_clarification":
            async for event in _run_clarification_route(
                route,
                query,
                conversation_id,
                history,
                checkpoint_writer,
            ):
                yield event
            return
        runtime_history = list(history)
        if resolution.ticker:
            runtime_history.append(
                Message(
                    role="system",
                    content=(self.resources.prompts or PromptRegistry.bundled()).render(
                        "session.resolved_instrument", ticker=resolution.ticker
                    ),
                    prompt_key="session.resolved_instrument",
                )
            )
        planning_context = _research_planning_context(conversation_context)
        if planning_context:
            runtime_history.append(
                Message(
                    role="system",
                    content=planning_context,
                )
            )
        loop_kwargs: dict[str, Any] = {
            "skill_registry": self.resources.skills or SkillRegistry.bundled(),
        }
        if self.resources.prompts is not None:
            loop_kwargs["prompt_registry"] = self.resources.prompts
        runtime = AgentLoop(
            model_service,
            self.tool_runner,
            config=AgentLoopConfig(
                mode=self.mode,
                model=_model_for_route(route, selected_provider),
                decision_provider=self.routing_policy,
                repair_model=(
                    settings.FINAI_CHATGPT_CODEX_TERRA_MODEL
                    if selected_provider == "chatgpt_codex"
                    else settings.HIVE_MODEL
                ),
                escalation_model=(
                    settings.FINAI_CHATGPT_CODEX_SOL_MODEL
                    if selected_provider == "chatgpt_codex"
                    else settings.HIVE_MODEL
                ),
                max_tokens=settings.HIVE_MAX_OUTPUT_TOKENS,
                report_max_tokens=settings.HIVE_MAX_REPORT_TOKENS,
                report_repair_max_tokens=settings.HIVE_MAX_REPAIR_TOKENS,
                max_run_seconds=settings.FINAI_AGENT_MAX_RUN_SECONDS,
                emergency_max_tool_calls=settings.FINAI_AGENT_EMERGENCY_MAX_TOOL_CALLS,
                max_input_tokens=settings.FINAI_AGENT_MAX_INPUT_TOKENS,
                duplicate_reuse_limit=settings.FINAI_AGENT_DUPLICATE_REUSE_LIMIT,
                max_report_repairs=settings.HIVE_MAX_REPORT_REPAIRS,
                report_repair_timeout_seconds=settings.HIVE_REPAIR_TIMEOUT,
                publish_reports=_wants_report(normalize_research_scope(query)),
                allowed_tools=(
                    frozenset(route.allowed_tools) if route is not None else None
                ),
                route_plan=route,
                resolved_ticker=resolution.ticker,
            ),
            **loop_kwargs,
        )
        async for event in runtime.run(
            runtime_history,
            conversation_id=conversation_id,
            approved_tool_ids=approved_tool_ids,
            checkpoint_writer=checkpoint_writer,
            message_writer=message_writer,
        ):
            yield event

    def _resolve_instrument_context(
        self,
        history: list[Message],
        query: str,
        conversation_id: UUID,
    ) -> tuple[InstrumentResolution, str]:
        explicit = resolve_instrument(query)
        if explicit.status == "resolved":
            return explicit, "explicit_query"
        if _has_instrument_reference(query):
            fetcher = self.resources.upstox_fetcher
            if fetcher is None:
                return (
                    InstrumentResolution("not_requested"),
                    "provider_unavailable",
                )
            try:
                resolved = resolve_instrument(query, fetcher.resolve_instrument)
            except Exception:  # noqa: BLE001 - provider failure becomes unresolved evidence
                resolved = InstrumentResolution(
                    "unresolved", reason="instrument search provider unavailable"
                )
            return resolved, "provider_search"
        cached = self._resolved_tickers.get(conversation_id) or _history_ticker(history)
        if cached:
            return InstrumentResolution("resolved", ticker=cached), "conversation_context"
        return InstrumentResolution("not_requested"), "not_requested"


def _model_for_route(route: RoutePlan | None, provider: str) -> str:
    if provider != "chatgpt_codex":
        return settings.HIVE_MODEL
    if route is not None and route.execution_mode is ExecutionMode.REPAIR:
        return settings.FINAI_CHATGPT_CODEX_TERRA_MODEL
    if route is not None and route.execution_mode is ExecutionMode.ESCALATE:
        return settings.FINAI_CHATGPT_CODEX_SOL_MODEL
    return settings.FINAI_CHATGPT_CODEX_LUNA_MODEL


_TICKER_TOKEN = re.compile(r"\b[A-Z][A-Z0-9.-]{1,14}\b")
_TICKER_STOPWORDS = {
    "WHAT",
    "THE",
    "CURRENT",
    "PRICE",
    "LATEST",
    "CLOSE",
    "OF",
    "FOR",
    "IS",
    "SHOW",
    "GET",
    "STOCK",
}
_EXCHANGE_TOKEN = re.compile(r"\b(?:NSE|BSE)\b", re.IGNORECASE)
_CANONICAL_TICKER = re.compile(r"\b[A-Z][A-Z0-9&-]{1,14}\.(?:NS|BO)\b", re.IGNORECASE)
_INSTRUMENT_MARKERS = re.compile(
    r"\b(?:analyse|analyze|research|stock|share|ticker|symbol|company|price|quote|"
    r"fundamental|technical|valuation|news|bank)\b",
    re.IGNORECASE,
)
_INSTRUMENT_STOPWORDS = {
    "ANALYSE",
    "ANALYZE",
    "RESEARCH",
    "STOCK",
    "SHARE",
    "TICKER",
    "SYMBOL",
    "COMPANY",
    "PRICE",
    "QUOTE",
    "FUNDAMENTAL",
    "TECHNICAL",
    "VALUATION",
    "NEWS",
    "BANK",
    "THE",
    "FOR",
    "LAST",
    "YEAR",
    "ONE",
    "CURRENT",
    "WHAT",
    "IS",
    "OF",
    "PLEASE",
    "YOU",
    "DO",
    "WITH",
    "ABOUT",
    "THIS",
    "THAT",
    "USE",
    "ANY",
    "EXCHANGE",
}


def _has_instrument_reference(query: str) -> bool:
    if _CANONICAL_TICKER.search(query.upper()):
        return True
    if not _INSTRUMENT_MARKERS.search(query):
        return False
    words = re.findall(r"\b[A-Z][A-Z0-9&-]{1,14}\b", query.upper())
    return any(word not in _INSTRUMENT_STOPWORDS for word in words)


def _history_ticker(history: list[Message]) -> str | None:
    for message in reversed(history):
        matches = _CANONICAL_TICKER.findall(message.content.upper())
        if matches:
            return matches[-1]
    return None


def _route_requests_instrument_clarification(route: RoutePlan) -> bool:
    text = " ".join(
        value
        for value in (route.reason, route.escalation_reason)
        if isinstance(value, str)
    ).casefold()
    return any(term in text for term in ("ticker", "instrument", "exchange", "symbol"))


def _direct_tool_arguments(route: RoutePlan, query: str) -> dict[str, object] | None:
    if len(route.required_tools) != 1:
        return None
    if route.required_tools[0] not in {
        "data:fetch_stock_data",
        "data:fetch_fundamentals",
        "analysis:get_technical_overview",
        "analysis:run_technical_scan",
        "news:fetch_news",
        "data:fetch_market_status",
        "data:fetch_market_holidays",
    }:
        return None
    if route.required_tools[0] == "data:fetch_market_status":
        exchange = next((token.upper() for token in _EXCHANGE_TOKEN.findall(query)), "NSE")
        return {"exchange": exchange}
    if route.required_tools[0] == "data:fetch_market_holidays":
        match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", query)
        return {"date": match.group(0) if match else ""}
    ticker = next(
        (
            token
            for token in _TICKER_TOKEN.findall(query.upper())
            if token not in _TICKER_STOPWORDS
        ),
        None,
    )
    if not ticker:
        return None
    return {"ticker": ticker}


async def _run_direct_tool(
    tool_runner: FinancialToolRunner,
    tool: str,
    arguments: dict[str, object],
    query: str,
    conversation_id: UUID,
    route: RoutePlan,
    message_writer: Callable[[Message], None] | None,
) -> AsyncIterator[ResearchEvent]:
    started = time.perf_counter()
    factory = EventFactory(conversation_id)
    yield factory.make(RunStarted, query=query)
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
    yield factory.make(StageStarted, stage="route", label="Using a direct data tool")
    yield factory.make(ToolStarted, tool=tool, tool_id="direct-route")
    try:
        payload = await tool_runner.execute(tool, arguments)
    except Exception as exc:  # noqa: BLE001 - direct route must terminate safely
        yield factory.make(
            ToolFailed, tool=tool, tool_id="direct-route", message=str(exc)
        )
        yield factory.make(
            RunCompleted,
            terminal_status="insufficient_data",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return
    if payload.get("success", True) is False:
        yield factory.make(
            ToolFailed,
            tool=tool,
            tool_id="direct-route",
            message=str(payload.get("error", "direct tool failed")),
        )
        yield factory.make(
            RunCompleted,
            terminal_status="insufficient_data",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return
    data = payload.get("data")
    provenance = payload.get("provenance")
    if (
        not data
        or not isinstance(provenance, dict)
        or not provenance.get("source")
        or not (provenance.get("observed_at") or provenance.get("as_of"))
    ):
        yield factory.make(
            ToolFailed,
            tool=tool,
            tool_id="direct-route",
            message="direct lookup returned incomplete provenance",
        )
        yield factory.make(
            RunCompleted,
            terminal_status="insufficient_data",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return
    text = json.dumps(
        {"data": payload.get("data", {}), "provenance": provenance},
        default=str,
        sort_keys=True,
    )
    yield factory.make(
        ToolCompleted,
        tool=tool,
        tool_id="direct-route",
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    if message_writer:
        message_writer(Message(role="assistant", content=text))
    yield factory.make(TextDelta, text=text)
    yield factory.make(
        RunCompleted,
        terminal_status="completed",
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        evidence_status="complete",
    )


def _research_planning_context(context: dict[str, Any]) -> str:
    tickers = context.get("comparison_tickers")
    focal = context.get("resolved_ticker")
    if not isinstance(tickers, list) or not focal:
        return ""
    normalized = [str(ticker) for ticker in tickers]
    from app.core.prompts import PromptRegistry

    return PromptRegistry.bundled().render(
        "session.research_plan",
        focal_ticker=str(focal),
        peer_universe=", ".join(normalized),
        default_timeframe=str(context.get("default_timeframe", "1y")),
    )


async def _run_denied_route(
    route: RoutePlan, query: str, conversation_id: UUID
) -> AsyncIterator[ResearchEvent]:
    factory = EventFactory(conversation_id)
    yield factory.make(RunStarted, query=query)
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
    message = (
        "I can't process that request because it conflicts with FIN-AI safety "
        "or authorization rules. Please restate the legitimate research goal."
    )
    yield factory.make(TextDelta, text=message)
    yield factory.make(RunCompleted, terminal_status="denied")


async def _run_clarification_route(
    route: RoutePlan,
    query: str,
    conversation_id: UUID,
    history: list[Message],
    checkpoint_writer: Callable[[dict[str, Any]], None] | None,
) -> AsyncIterator[ResearchEvent]:
    factory = EventFactory(conversation_id)
    yield factory.make(RunStarted, query=query)
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
    prompt = (
        route.escalation_reason or route.reason
        if route.reason and not route.reason.casefold().startswith("jev selected")
        else "Please clarify the request so I can continue safely."
    )
    if checkpoint_writer:
        checkpoint_writer(
            {
                "messages": [message.model_dump(mode="json") for message in history],
                "tool_name": "interaction:ask_user",
                "arguments": {"question": prompt},
                "status": "awaiting_clarification",
            }
        )
    yield factory.make(ClarificationRequested, prompt=prompt)
    yield factory.make(RunCompleted, terminal_status="awaiting_clarification")
