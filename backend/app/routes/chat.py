"""HTTP streaming adapter for the same runtime used by the FIN-AI CLI."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import uuid4

from app.config import settings
from app.core.agent_loop import AgentLoop, AgentLoopConfig, RegistryToolRunner
from app.core.node_resources import resources
from app.core.skills import SkillRegistry
from app.core.tools.tool_system import (
    initialize_tool_system,
    tool_executor,
    tool_registry,
)
from app.events.models import ResearchEvent
from app.models.request_models import ChatRequest
from app.models.response_models import StreamEvent
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

router = APIRouter()


def _runtime(request: ChatRequest) -> AgentLoop:
    initialize_tool_system()
    return AgentLoop(
        resources.llm_service,
        RegistryToolRunner(tool_registry, tool_executor),
        config=AgentLoopConfig(
            model=request.model or settings.HIVE_MODEL,
            max_tokens=request.max_tokens or settings.HIVE_MAX_OUTPUT_TOKENS,
            mode="autonomous",
        ),
        skill_registry=SkillRegistry.bundled(),
    )


class _SharedRuntimeOrchestrator:
    """Compatibility seam for callers that patch ``orchestrator.execute_query``."""

    async def execute_query(
        self,
        query: str,
        *,
        conversation_history: list,
        **_: object,
    ) -> AsyncIterator[StreamEvent]:
        request = ChatRequest(messages=conversation_history)
        async for event in _runtime(request).run(
            conversation_history,
            conversation_id=uuid4(),
        ):
            mapped = _to_sse_event(event)
            if mapped is not None:
                yield mapped


# Kept for source compatibility with integrations and tests. Production calls
# still execute through the shared AgentLoop implementation above.
orchestrator = _SharedRuntimeOrchestrator()


@router.post("/chat")
async def chat_endpoint(request: ChatRequest) -> StreamingResponse:
    user_query = next(
        (message.content for message in reversed(request.messages) if message.role == "user"),
        "",
    )
    if not user_query:
        raise HTTPException(status_code=400, detail="No user message found.")

    async def event_generator() -> AsyncIterator[str]:
        yield ": " + (" " * 1024) + "\n\n"
        try:
            events = orchestrator.execute_query(
                user_query,
                conversation_history=request.messages,
            )
            async for event in events:
                yield f"data: {json.dumps(event.model_dump())}\n\n"
        except Exception as exc:  # noqa: BLE001 - HTTP stream boundary
            yield f"data: {json.dumps(StreamEvent(type='error', message=str(exc)).model_dump())}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _to_sse_event(event: ResearchEvent) -> StreamEvent | None:
    if event.type == "response.delta":
        return StreamEvent(type="text_delta", content=event.text)
    if event.type == "stage.started":
        return StreamEvent(type="status", message=event.label)
    if event.type == "skill.selected":
        return StreamEvent(type="status", message=f"Using {event.skill_id}")
    if event.type == "model.request.started":
        return StreamEvent(type="status", message="Contacting research model")
    if event.type == "provider.attempt.started":
        return StreamEvent(type="status", message=f"Contacting Hive · attempt {event.attempt}")
    if event.type == "provider.retrying":
        return StreamEvent(
            type="status",
            message=f"Retrying Hive · {event.reason} · {event.delay_ms / 1000:.1f}s",
        )
    if event.type == "provider.stream.started":
        return StreamEvent(
            type="status",
            message=f"Hive stream started · {event.first_byte_ms / 1000:.1f}s",
        )
    if event.type == "provider.failed":
        return StreamEvent(type="error", message=event.message)
    if event.type == "tool.started":
        return StreamEvent(
            type="tool_status",
            tool_id=event.tool_id,
            tool_name=event.tool,
            status="running",
            input=event.detail,
        )
    if event.type == "tool.progress":
        return StreamEvent(
            type="tool_status",
            tool_id=event.tool_id,
            tool_name=event.tool,
            status="running",
            message=event.message,
        )
    if event.type == "tool.completed":
        return StreamEvent(
            type="tool_status",
            tool_id=event.tool_id,
            tool_name=event.tool,
            status="completed",
            output=event.detail,
        )
    if event.type == "tool.failed":
        return StreamEvent(
            type="tool_status",
            tool_id=event.tool_id,
            tool_name=event.tool,
            status="error",
            message=event.message,
        )
    if event.type == "approval.requested":
        return StreamEvent(type="approval_required", message=event.prompt, data=event.details)
    if event.type == "clarification.requested":
        return StreamEvent(type="clarification_required", message=event.prompt)
    if event.type == "run.failed":
        return StreamEvent(type="error", message=event.message)
    if event.type == "run.cancelled":
        return StreamEvent(type="run_cancelled", message=event.reason)
    if event.type == "run.completed":
        return StreamEvent(type="done", data={"status": event.terminal_status})
    return None
