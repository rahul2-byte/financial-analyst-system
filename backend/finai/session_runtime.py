"""Production research runner used by the terminal session facade."""

from __future__ import annotations

import contextlib
import datetime
import json
import re
import time
from collections.abc import AsyncIterator, Callable
from typing import Any, TypeGuard
from uuid import UUID

from app.config import settings
from app.core.agent_loop import AgentLoop, AgentLoopConfig, FinancialToolRunner
from app.core.agent_loop.evidence import valid_provenance
from app.core.agent_loop.publication import (
    # Private on purpose: publication.py is owned elsewhere; reuse its exact
    # numeric-claim definition so freeform and report grounding cannot drift.
    _NUMBER,
    EvidenceFact,
    report_validation_fallback,
)
from app.core.agent_loop.tool_execution import ToolExecutor
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
        # Read-only handle on the latest loop, for presentation material.
        self.last_loop: AgentLoop | None = None

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
        self.last_loop = None
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
        conversation_context["conversation_id"] = str(conversation_id)
        if self.routing_policy is not None:
            selected_skills = (self.resources.skills or SkillRegistry.bundled()).select(
                query
            )
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
        if route is not None and route.model_tier in {
            ModelTier.SMALL,
            ModelTier.MAIN,
        }:
            selected_model = settings.OPENROUTER_MODEL
            route = route.model_copy(
                update={
                    "selected_provider": "openrouter",
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
                    "escalation_reason": resolution.reason,
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
            direct_arguments = _direct_tool_arguments(route, query, resolution)
            if _is_ticker_tool(route) and resolution.status in {
                "ambiguous",
                "unresolved",
            }:
                clarification = route.model_copy(
                    update={
                        "execution_mode": ExecutionMode.DETERMINISTIC,
                        "next_action": NextAction.ASK_CLARIFICATION,
                        "reason": resolution.reason
                        or "Instrument identity is ambiguous.",
                        "escalation_reason": resolution.reason,
                        "required_tools": [],
                        "allowed_tools": set(),
                    }
                )
                async for event in _run_clarification_route(
                    clarification, query, conversation_id, history, checkpoint_writer
                ):
                    yield event
                return
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
        publish_reports = _wants_report(normalize_research_scope(query))
        answer_contract = (
            "report"
            if publish_reports
            else "lookup"
            if route is not None and len(route.required_tools) == 1
            else "freeform"
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
                model=settings.OPENROUTER_MODEL,
                decision_provider=self.routing_policy,
                repair_model=settings.OPENROUTER_MODEL,
                escalation_model=settings.OPENROUTER_MODEL,
                max_tokens=settings.OPENROUTER_MAX_OUTPUT_TOKENS,
                report_max_tokens=settings.OPENROUTER_MAX_REPORT_TOKENS,
                report_repair_max_tokens=settings.OPENROUTER_MAX_REPAIR_TOKENS,
                max_run_seconds=settings.FINAI_AGENT_MAX_RUN_SECONDS,
                emergency_max_tool_calls=settings.FINAI_AGENT_EMERGENCY_MAX_TOOL_CALLS,
                max_input_tokens=settings.FINAI_AGENT_MAX_INPUT_TOKENS,
                duplicate_reuse_limit=settings.FINAI_AGENT_DUPLICATE_REUSE_LIMIT,
                max_report_repairs=settings.OPENROUTER_MAX_REPORT_REPAIRS,
                report_repair_timeout_seconds=settings.OPENROUTER_REPAIR_TIMEOUT,
                publish_reports=publish_reports,
                answer_contract=answer_contract,
                allowed_tools=(
                    frozenset(route.allowed_tools) if route is not None else None
                ),
                route_plan=route,
                resolved_ticker=resolution.ticker,
            ),
            **loop_kwargs,
        )
        self.last_loop = runtime
        stream = runtime.run(
            runtime_history,
            conversation_id=conversation_id,
            approved_tool_ids=approved_tool_ids,
            checkpoint_writer=checkpoint_writer,
            message_writer=(
                _grounded_message_writer(self.tool_runner, message_writer)
                if answer_contract == "freeform"
                else message_writer
            ),
        )
        if answer_contract == "freeform":
            self.tool_runner.reset_turn_evidence()
            stream = _ground_freeform_stream(self.tool_runner, stream)
        async for event in stream:
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
                bare = _single_bare_symbol(query)
                if bare:
                    return (
                        InstrumentResolution("resolved", ticker=bare),
                        "bare_symbol",
                    )
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
            return InstrumentResolution(
                "resolved", ticker=cached
            ), "conversation_context"
        return InstrumentResolution("not_requested"), "not_requested"


_EXCHANGE_TOKEN = re.compile(r"\b(?:NSE|BSE)\b", re.IGNORECASE)
_CANONICAL_TICKER = re.compile(r"\b[A-Z][A-Z0-9&-]{1,14}\.(?:NS|BO)\b", re.IGNORECASE)
_INSTRUMENT_MARKERS = re.compile(
    r"\b(?:analyse|analyze|research|stock|share|ticker|symbol|company|price|quote|"
    r"fundamental|technical|valuation|news|bank)\b",
    re.IGNORECASE,
)
_BARE_EXTRA_STOPWORDS = {
    "NSE",
    "BSE",
    "WHATS",
    "GIVE",
    "TELL",
    "FETCH",
    "ME",
    "LIVE",
    "SHOW",
    "GET",
    "TO",
}
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


def _single_bare_symbol(query: str) -> str | None:
    """Return the only plausible bare NSE symbol; default suffix is applied by tools."""
    tokens = {
        token
        for token in re.findall(r"\b[A-Z][A-Z0-9&-]{1,14}\b", query.upper())
        if token not in _INSTRUMENT_STOPWORDS and token not in _BARE_EXTRA_STOPWORDS
    }
    if len(tokens) != 1:
        return None
    return next(iter(tokens))


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


def _direct_tool_arguments(
    route: RoutePlan, query: str, resolution: InstrumentResolution | None = None
) -> dict[str, object] | None:
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
        exchange = next(
            (token.upper() for token in _EXCHANGE_TOKEN.findall(query)), "NSE"
        )
        return {"exchange": exchange}
    if route.required_tools[0] == "data:fetch_market_holidays":
        match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", query)
        return {"date": match.group(0) if match else ""}
    # Tickers come only from the instrument resolver; an empty ticker never
    # reaches a provider (ambiguous/unresolved take the clarification path).
    if resolution is None or resolution.status != "resolved" or not resolution.ticker:
        return None
    return {"ticker": resolution.ticker}


def _is_ticker_tool(route: RoutePlan) -> bool:
    return len(route.required_tools) == 1 and route.required_tools[0] not in {
        "data:fetch_market_status",
        "data:fetch_market_holidays",
    }


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
    # Same allowlist, argument validation, timeout and error normalisation as
    # tools called by the AgentLoop.
    payload = await ToolExecutor(tool_runner, set(route.allowed_tools)).execute(
        tool, arguments
    )
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
        or not valid_provenance(payload)
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
    full_json = json.dumps(
        {"data": payload.get("data", {}), "provenance": provenance},
        default=str,
        sort_keys=True,
    )
    text = format_direct_answer(
        tool, data, provenance, payload.get("key_values")
    ) or _compact_listing(data, provenance)
    yield factory.make(
        ToolCompleted,
        tool=tool,
        tool_id="direct-route",
        detail=full_json,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    if message_writer:
        message_writer(Message(role="assistant", content=full_json))
    yield factory.make(TextDelta, text=text)
    yield factory.make(
        RunCompleted,
        terminal_status="completed",
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        evidence_status=(
            "limited" if provenance.get("quality_status") == "degraded" else "complete"
        ),
    )


_PERIOD_LABELS = {
    "1d": "1-day", "5d": "5-day", "1mo": "1-month", "3mo": "3-month",
    "6mo": "6-month", "1y": "1-year", "2y": "2-year", "5y": "5-year",
}  # fmt: skip
_SOURCE_LABELS = {"yfinance": "Yahoo Finance", "upstox": "Upstox"}


def _signed_pct(value: float) -> str:
    sign = "+" if value >= 0 else "\u2212"
    return f"{sign}{abs(value):.1f}%"


_TECH_TOOLS = {"analysis:get_technical_overview", "analysis:run_technical_scan"}
_FUND_TOOLS = {"analysis:run_fundamental_scan", "data:fetch_fundamentals"}
# Field names mirror tool_runner._technical_key_values / _fundamental_key_values.
_TECH_FIELDS = (
    ("SMA_20", "SMA20"), ("SMA_50", "SMA50"), ("SMA_200", "SMA200"),
    ("MACD_12_26_9", "MACD"), ("MACD_SIGNAL_12_26_9", "MACD signal"),
    ("BBANDS_UPPER_20_2", "BB upper"), ("BBANDS_LOWER_20_2", "BB lower"),
)  # fmt: skip
_FUND_FIELDS = (
    ("peRatio", "P/E"), ("forwardPE", "Fwd P/E"), ("priceToBook", "P/B"),
    ("returnOnEquity", "ROE"), ("debtToEquity", "Debt/Equity"),
    ("marketCapCrore", "Mkt cap (Cr)"), ("marketCap", "Mkt cap"),
)  # fmt: skip


def _num(value: Any, digits: int = 2) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return "n/a"
    return f"{value:,.{digits}f}"


def _is_number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _source_line(provenance: dict[str, Any]) -> str:
    source = _SOURCE_LABELS.get(
        str(provenance.get("source")), str(provenance.get("source"))
    )
    as_of = provenance.get("as_of") or provenance.get("observed_at")
    return f"Source: {source}, as of {as_of}."


def _compact_listing(data: Any, provenance: dict[str, Any]) -> str:
    """Fallback: top-level scalar fields as ``key: value`` lines, never raw JSON."""
    items = data.items() if isinstance(data, dict) else []
    lines = [
        f"{k}: {v}"
        for k, v in items
        if v is None or isinstance(v, str | int | float | bool)
    ][:8]
    if not lines:
        lines = ["Data retrieved; open the event detail for the full payload."]
    return "\n".join([*lines, _source_line(provenance)])


def _technical_answer(
    data: dict[str, Any], provenance: dict[str, Any], key_values: Any
) -> str | None:
    kv: dict[str, Any] = dict(key_values) if isinstance(key_values, dict) else {}
    if not kv:
        for item in data.get("measurements") or []:
            if isinstance(item, dict) and item.get("indicator"):
                kv[str(item["indicator"])] = item.get("value")
        kv["as_of"] = data.get("as_of")
    ticker = str(data.get("ticker") or provenance.get("instrument") or "").strip()
    if not ticker or not kv:
        return None
    day = str(kv.get("as_of") or data.get("as_of") or "")[:10] or "n/a"
    interval = {"1d": "daily", "1wk": "weekly", "1mo": "monthly"}.get(
        str(data.get("interval")), str(data.get("interval") or "n/a")
    )
    rsi = kv.get("RSI_14")
    rsi_text = f"RSI(14) {_num(rsi, 1)}"
    if isinstance(rsi, int | float) and not isinstance(rsi, bool):
        if rsi > 70:
            rsi_text += " (overbought >70)"
        elif rsi < 30:
            rsi_text += " (oversold <30)"
    close = f"close {_num(kv.get('close'))}"
    if provenance.get("currency") == "INR" and isinstance(kv.get("close"), int | float):
        close = f"close ₹{kv['close']:,.2f}"
    parts = [close, rsi_text]
    parts += [f"{lab} {_num(kv.get(key))}" for key, lab in _TECH_FIELDS]
    head = f"{ticker} technicals as of {day} ({interval}): "
    return "\n".join([head + " · ".join(parts), _source_line(provenance)])


def _fundamental_answer(data: dict[str, Any], provenance: dict[str, Any]) -> str | None:
    if not any(data.get(key) is not None for key, _ in _FUND_FIELDS):
        return None
    ticker = str(data.get("ticker") or provenance.get("instrument") or "").strip()
    parts = []
    for key, lab in _FUND_FIELDS:
        value = data.get(key)
        if key == "returnOnEquity" and _is_number(value):
            parts.append(f"{lab} {_num(value * 100, 1)}%")  # fraction -> percent
        elif key == "debtToEquity" and _is_number(value):
            parts.append(f"{lab} {_num(value)}x")  # provider normalises to a ratio
        else:
            parts.append(f"{lab} {_num(value)}")
    head = f"{ticker or 'Fundamentals'} key fundamentals: "
    return "\n".join([head + " · ".join(parts), _source_line(provenance)])


def format_direct_answer(
    tool: str,
    data: Any,
    provenance: dict[str, Any],
    key_values: Any = None,
) -> str | None:
    """Plain-text answer for a direct tool, formatted from payload fields only."""
    if not isinstance(data, dict):
        return None
    if tool in _TECH_TOOLS:
        return _technical_answer(data, provenance, key_values)
    if tool in _FUND_TOOLS:
        return _fundamental_answer(data, provenance)
    if tool != "data:fetch_stock_data":
        return None
    latest = data.get("latest")
    if not isinstance(latest, dict) or not isinstance(latest.get("Close"), int | float):
        return None
    ticker = str(data.get("ticker") or provenance.get("instrument") or "").strip()
    if not ticker:
        return None
    currency = provenance.get("currency")
    symbol = {"INR": "\u20b9", "USD": "$"}.get(str(currency), "")
    price = f"{symbol}{latest['Close']:,.2f}" + (
        f" {currency}" if currency and not symbol else ""
    )
    when = ""
    raw_date = str(latest.get("Date") or "")[:10]
    with contextlib.suppress(ValueError):
        when = f" on {datetime.date.fromisoformat(raw_date):%d %b %Y}"
    changes = []
    day = data.get("day_change_pct")
    if isinstance(day, int | float):
        changes.append(f"{_signed_pct(float(day))} on the day")
    period_return = data.get("period_return_pct")
    if isinstance(period_return, int | float):
        label = _PERIOD_LABELS.get(
            str(data.get("period")), str(data.get("period") or "")
        )
        changes.append(f"{label} {_signed_pct(float(period_return))}".strip())
    suffix = f" ({'; '.join(changes)})" if changes else ""
    source = _SOURCE_LABELS.get(
        str(provenance.get("source")), str(provenance.get("source"))
    )
    as_of = provenance.get("as_of") or provenance.get("observed_at")
    return (
        f"{ticker} last close {price}{when}{suffix}. Source: {source}, as of {as_of}."
    )


_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)"
)
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ][\d:.+-]+Z?)?")
_LIST_MARKER = re.compile(r"(?m)^\s*(?:[-*]\s+)?\d{1,2}[.)]\s")
_CURRENCY_PREFIX = re.compile(r"(?:₹|\bRs\.?|\bINR)\s*", re.IGNORECASE)
_DAY_MONTH = re.compile(
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH}\b\.?(?:,?\s+\d{{4}})?"
    rf"|\b{_MONTH}\b\.?\s+\d{{1,2}}(?:st|nd|rd|th)?\b(?:,?\s+\d{{4}})?",
    re.IGNORECASE,
)
_TIME = re.compile(r"(?<![\d.])\d{1,2}:\d{2}(?::\d{2})?\b")
# Standalone 1990-2100 (also after FY/CY/Q1-4); never part of 2,050 or 2050.5.
_YEAR = re.compile(r"(?<![\d.,])(?:19[9]\d|20\d\d|2100)(?![\d]|\.\d|,\d)")
_PERIOD_WORD = re.compile(
    r"(?<![\d.])\d+(?:\.\d+)?[\s-]*(?:days?|weeks?|wks?|months?|mos?|years?|yrs?|"
    r"periods?|sessions?|DMA|SMA|EMA)\b",
    re.IGNORECASE,
)
_INDICATOR_PARAMS = re.compile(
    r"\b(?:SMA|EMA|DMA|WMA|RSI|MACD|ATR|ADX|ROC|CCI|BB|MA)\s*\(?\s*"
    r"\d+(?![\d.]\d)(?:\s*[/,]\s*\d+(?![\d.]\d))*\s*\)?",
    re.IGNORECASE,
)
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_NUMBER_SCALES = {
    "tn": 1e12, "bn": 1e9, "b": 1e9, "mn": 1e6, "m": 1e6, "cr": 1e7,
    "crore": 1e7, "crores": 1e7, "lakh": 1e5, "lakhs": 1e5, "k": 1e3,
}  # fmt: skip


def _claim_numbers(text: str) -> list[str]:
    """Numbers in ``text`` that read as financial claims, not dates or parameters."""
    text = re.sub(r"\[\[fact:[^\]]*\]\]", "", text)
    for pattern in (
        _ISO_DATE, _DAY_MONTH, _TIME, _YEAR, _PERIOD_WORD, _INDICATOR_PARAMS,
        _LIST_MARKER,
    ):  # fmt: skip
        text = pattern.sub(" ", text)
    text = _CURRENCY_PREFIX.sub("", _THOUSANDS.sub("", text))
    return _NUMBER.findall(text)


def _number_is_bound(token: str, facts: dict[str, EvidenceFact]) -> bool:
    match = re.fullmatch(r"([+-]?[\d.]+)(%|[A-Za-z]*)", token)
    if match is None:
        return True
    try:
        number = abs(float(match.group(1)))
    except ValueError:
        return True
    suffix = match.group(2).lower()
    if not suffix and number == int(number) and number <= 10:
        return True  # counts such as "three risks" are not financial claims
    scales = (1.0, 0.01) if suffix == "%" else (_NUMBER_SCALES.get(suffix, 1.0), 1.0)
    for fact in facts.values():
        if isinstance(fact.value, str):
            continue
        value = abs(float(fact.value))
        for scale in scales:
            for candidate in (value / scale, value * 100 / scale):
                if abs(candidate - number) <= max(abs(candidate) * 0.01, 0.01):
                    return True
    return False


def _grounded_text(tool_runner: FinancialToolRunner, text: str) -> str:
    """Fail closed when a freeform answer shows numbers no tool evidence supports."""
    if tool_runner.turn_evidence_tools == 0:
        return text
    facts = tool_runner.turn_facts
    if all(_number_is_bound(token, facts) for token in _claim_numbers(text)):
        return text
    return report_validation_fallback(facts, ("numeric_claim_unbound",))


def _grounded_message_writer(
    tool_runner: FinancialToolRunner,
    writer: Callable[[Message], None] | None,
) -> Callable[[Message], None] | None:
    if writer is None:
        return None

    def write(message: Message) -> None:
        if message.role == "assistant" and isinstance(message.content, str):
            message = message.model_copy(
                update={"content": _grounded_text(tool_runner, message.content)}
            )
        writer(message)

    return write


async def _ground_freeform_stream(
    tool_runner: FinancialToolRunner, stream: AsyncIterator[ResearchEvent]
) -> AsyncIterator[ResearchEvent]:
    """Hold answer text once evidence tools ran, so it can be checked before display."""
    held: list[TextDelta] = []

    def flush() -> list[ResearchEvent]:
        if not held:
            return []
        text = "".join(event.text for event in held)
        grounded = _grounded_text(tool_runner, text)
        events: list[ResearchEvent] = (
            [held[0].model_copy(update={"text": grounded})]
            if grounded != text
            else list(held)
        )
        held.clear()
        return events

    async for event in stream:
        if isinstance(event, TextDelta) and tool_runner.turn_evidence_tools:
            held.append(event)
            continue
        if isinstance(event, RunCompleted):
            for item in flush():
                yield item
        yield event
    for item in flush():
        yield item


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
