"""HTTP streaming adapter for the same runtime used by the FIN-AI CLI."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import AsyncIterator
from hmac import compare_digest
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from app.config import settings
from app.core.agent_loop import AgentLoop, AgentLoopConfig, FinancialToolRunner
from app.core.query_scope import normalize_research_scope
from app.core.resources import build_runtime_resources
from app.core.skills import SkillRegistry
from app.events.models import ResearchEvent
from app.models.request_models import ChatRequest, Message
from app.models.response_models import StreamEvent
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from finai.session_store import SessionStore

router = APIRouter()
logger = logging.getLogger(__name__)


def _runtime(request: ChatRequest) -> AgentLoop:
    runtime_resources = build_runtime_resources()
    return AgentLoop(
        runtime_resources.llm_service,
        FinancialToolRunner(runtime_resources),
        config=AgentLoopConfig(
            model=request.model or settings.HIVE_MODEL,
            max_tokens=request.max_tokens or settings.HIVE_MAX_OUTPUT_TOKENS,
            report_max_tokens=settings.HIVE_MAX_REPORT_TOKENS,
            mode="autonomous",
            publish_reports=request.publish_report or _requires_report(request),
        ),
        skill_registry=SkillRegistry.bundled(),
    )


def _requires_report(request: ChatRequest) -> bool:
    query = next(
        (
            message.content
            for message in reversed(request.messages)
            if message.role == "user"
        ),
        "",
    )
    lowered = normalize_research_scope(query).casefold()
    return any(
        marker in lowered
        for marker in (
            "analyse ",
            "analyze ",
            "research ",
            "investment thesis",
            "technical analysis",
            "fundamental analysis",
            "financial analysis",
            "rsi",
            "macd",
            "valuation",
            "sentiment",
            "news",
            "stock",
            "company",
        )
    )


def _authenticated_owner(authorization: str | None) -> str:
    """Authenticate the HTTP boundary without logging bearer credentials."""
    token = settings.HTTP_API_TOKEN
    expected = f"Bearer {token}" if token else ""
    if not token or not authorization or not compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Authentication required")
    return settings.HTTP_API_OWNER


def _conversation_id(owner: str, session_id: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"finai:http:{owner}:{session_id}")


@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    owner = _authenticated_owner(authorization)
    user_query = next(
        (
            message.content
            for message in reversed(request.messages)
            if message.role == "user"
        ),
        "",
    )
    if not user_query:
        raise HTTPException(status_code=400, detail="No user message found.")

    session_id = request.session_id or uuid4().hex
    storage_id = hashlib.sha256(f"{owner}:{session_id}".encode()).hexdigest()[:32]
    store = SessionStore(Path(settings.HTTP_SESSION_ROOT), storage_id)
    history = store.load_history()
    history.append(Message(role="user", content=user_query))
    store.append_message(history[-1])

    async def event_generator() -> AsyncIterator[str]:
        yield ": " + (" " * 1024) + "\n\n"
        request_id = uuid4().hex
        try:
            events = _runtime(request).run(
                history,
                conversation_id=_conversation_id(owner, session_id),
                checkpoint_writer=store.write_checkpoint,
                message_writer=store.append_message,
            )
            async for event in events:
                safe_event = _to_sse_event(event)
                if safe_event is not None:
                    yield f"data: {json.dumps(safe_event.model_dump())}\n\n"
        except Exception:
            logger.exception("chat stream failed request_id=%s", request_id)
            yield (
                "data: "
                + json.dumps(
                    StreamEvent(
                        type="error",
                        message=f"The research request failed. Reference: {request_id}",
                    ).model_dump()
                )
                + "\n\n"
            )
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-FINAI-Session": session_id,
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
        return StreamEvent(
            type="status", message=f"Contacting Hive · attempt {event.attempt}"
        )
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
        return StreamEvent(type="error", message="The research provider failed.")
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
            message="The research tool failed.",
        )
    if event.type == "sources.updated":
        return StreamEvent(type="final_payload", data={"sources": event.sources})
    if event.type == "approval.requested":
        return StreamEvent(
            type="approval_required", message=event.prompt, data=event.details
        )
    if event.type == "clarification.requested":
        return StreamEvent(type="clarification_required", message=event.prompt)
    if event.type == "run.failed":
        return StreamEvent(type="error", message="The research request failed.")
    if event.type == "run.cancelled":
        return StreamEvent(type="run_cancelled", message=event.reason)
    if event.type == "run.completed":
        return StreamEvent(
            type="done",
            data={
                "status": event.terminal_status,
                "run_id": str(event.meta.run_id),
            },
        )
    return None
