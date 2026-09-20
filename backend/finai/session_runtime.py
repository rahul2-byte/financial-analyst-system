"""Production research runner used by the terminal session facade."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID

from app.config import settings
from app.core.agent_loop import AgentLoop, AgentLoopConfig, FinancialToolRunner
from app.core.query_scope import normalize_research_scope
from app.core.resources import RuntimeResources
from app.core.skills import SkillRegistry
from app.events.models import ResearchEvent
from app.models.request_models import Message


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
        self.hive_service = resources.llm_service
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
        runtime = AgentLoop(
            self.hive_service,
            self.tool_runner,
            config=AgentLoopConfig(
                mode=self.mode,
                model=settings.HIVE_MODEL,
                max_tokens=settings.HIVE_MAX_OUTPUT_TOKENS,
                report_max_tokens=settings.HIVE_MAX_REPORT_TOKENS,
                report_repair_max_tokens=settings.HIVE_MAX_REPAIR_TOKENS,
                report_repair_timeout_seconds=settings.HIVE_REPAIR_TIMEOUT,
                publish_reports=_wants_report(normalize_research_scope(query)),
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
