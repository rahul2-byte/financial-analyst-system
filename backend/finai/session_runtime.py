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
from app.core.query_scope import normalize_research_scope
from app.core.resources import RuntimeResources
from app.core.skills import SkillRegistry
from app.events.models import (
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
from app.models.routing import ExecutionMode, ModelTier, RoutePlan


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
        self.model_service = resources.llm_service
        self.routing_policy = resources.routing_policy
        self.mode = mode
        self.tool_runner = FinancialToolRunner(resources)

    async def stream(
        self,
        history: list[Message],
        query: str,
        conversation_id: UUID,
        *,
        approved_tool_ids: set[str] | None = None,
        checkpoint_writer: Callable[[dict[str, Any]], None] | None = None,
        message_writer: Callable[[Message], None] | None = None,
    ) -> AsyncIterator[ResearchEvent]:
        """Yield events for ``query`` while keeping construction out of the session."""
        route = None
        if self.routing_policy is not None:
            selected_skills = SkillRegistry.bundled().select(query)
            route = await self.routing_policy.decide(
                query,
                available_tools={
                    str(item.get("function", {}).get("name"))
                    for item in self.tool_runner.definitions()
                },
                available_skills={skill.manifest.id for skill in selected_skills},
            )
        model_service = self.model_service
        if route is not None and route.model_tier is ModelTier.MAIN:
            route = route.model_copy(
                update={
                    "selected_provider": "hive",
                    "selected_model": settings.HIVE_MODEL,
                }
            )
        if route is not None and route.execution_mode is ExecutionMode.TOOL_ONLY:
            direct_arguments = _direct_tool_arguments(route, query)
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
        runtime = AgentLoop(
            model_service,
            self.tool_runner,
            config=AgentLoopConfig(
                mode=self.mode,
                model=settings.HIVE_MODEL,
                max_tokens=settings.HIVE_MAX_OUTPUT_TOKENS,
                report_max_tokens=settings.HIVE_MAX_REPORT_TOKENS,
                report_repair_max_tokens=settings.HIVE_MAX_REPAIR_TOKENS,
                report_repair_timeout_seconds=settings.HIVE_REPAIR_TIMEOUT,
                publish_reports=_wants_report(normalize_research_scope(query)),
                allowed_tools=(
                    frozenset(route.allowed_tools) if route is not None else None
                ),
                route_plan=route,
            ),
            skill_registry=SkillRegistry.bundled(),
        )
        async for event in runtime.run(
            history,
            conversation_id=conversation_id,
            approved_tool_ids=approved_tool_ids,
            checkpoint_writer=checkpoint_writer,
            message_writer=message_writer,
        ):
            yield event


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


def _direct_tool_arguments(route: RoutePlan, query: str) -> dict[str, object] | None:
    if len(route.required_tools) != 1:
        return None
    if route.required_tools[0] not in {
        "data:fetch_stock_data",
        "data:fetch_fundamentals",
        "analysis:get_technical_overview",
        "analysis:run_technical_scan",
        "news:fetch_news",
    }:
        return None
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
    text = json.dumps(payload.get("data", payload), default=str, sort_keys=True)
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
