"""Production research runner used by the terminal session facade."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID

from app.config import settings
from app.core.agent_loop import AgentLoop, AgentLoopConfig, FinancialToolRunner
from app.core.resources import RuntimeResources
from app.events.models import ResearchEvent
from app.models.request_models import Message


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
        del query
        runtime = AgentLoop(
            self.hive_service,
            self.tool_runner,
            config=AgentLoopConfig(
                mode=self.mode,
                model=settings.HIVE_MODEL,
                max_tokens=settings.HIVE_MAX_OUTPUT_TOKENS,
            ),
        )
        async for event in runtime.run(
            history,
            conversation_id=conversation_id,
            approved_tool_ids=approved_tool_ids,
            checkpoint_writer=checkpoint_writer,
            message_writer=message_writer,
        ):
            yield event
