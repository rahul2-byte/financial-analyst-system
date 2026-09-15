"""Conversation state, runtime streaming, and local persistence."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.diagnostics import diagnostic_payload, diagnostics_enabled
from app.core.tools.tool_system import tool_executor, tool_registry
from app.events.models import EventFactory, ResearchEvent, RunCancelled
from app.models.request_models import Message
from app.services.hive_service import HiveService

from .context_budget import ContextBudget
from .session_persistence import SessionPersistence
from .session_runtime import ResearchRunner
from .session_store import SessionStore
from .stream_adapter import adapt_legacy_stream
from .supervisor import supervise

logger = logging.getLogger(__name__)


class FinAIRepl:
    def __init__(self, root: Path | None = None, session_id: str | None = None) -> None:
        self.root = root or Path(".finai")
        self.session_id = session_id or uuid.uuid4().hex
        self.store = SessionStore(self.root, self.session_id)
        self.persistence = SessionPersistence(self.store)
        self.mode = "guided"
        self.history: list[Message] = []
        self._load_session()
        self.hive_service = HiveService()
        self.runtime = ResearchRunner(
            self.hive_service,
            self.mode,
            tool_registry,
            tool_executor,
        )
        # Production CLI uses AgentLoop directly. Tests and integrations may
        # still inject a legacy stream adapter through this compatibility slot.
        self.orchestrator: Any | None = None

    @property
    def conversation_id(self) -> uuid.UUID:
        try:
            return uuid.UUID(self.session_id)
        except ValueError:
            return uuid.uuid5(uuid.NAMESPACE_URL, f"finai:{self.session_id}")

    @property
    def session_dir(self) -> Path:
        return self.root / "sessions" / self.session_id

    def _load_session(self) -> None:
        self.store.mark_incomplete_runs_interrupted()
        self.history = self.store.load_history()

    def resume_session(self, session_id: str) -> None:
        self.session_id = session_id
        self.store = SessionStore(self.root, session_id)
        self.persistence = SessionPersistence(self.store)
        self.history = self.persistence.load_history()

    def new_session(self) -> None:
        self.resume_session(uuid.uuid4().hex)

    def compact_context(self) -> dict[str, int | str]:
        return self._compact_history(include_budget=True)

    def _compact_history(self, *, include_budget: bool = False) -> dict[str, int | str]:
        """Compact history once and persist the resulting context metadata."""
        budget = ContextBudget(
            max_tokens=settings.FINAI_CONTEXT_MAX_TOKENS,
            compaction_ratio=settings.FINAI_CONTEXT_COMPACTION_RATIO,
        )
        self.history, result = budget.compact(self.history)
        if result["compacted_messages"]:
            context: dict[str, int | str] = {
                **result,
                "message_count": len(self.history),
            }
            if include_budget:
                context.update(
                    max_tokens=budget.max_tokens,
                    compaction_limit=budget.compaction_limit,
                )
            self.store.write_context(context)
        return result

    def _write_session(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        target = self.session_dir / "session.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"session_id": self.session_id, "history": [item.model_dump() for item in self.history]}, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)

    def _write_run(self, query: str, events: list[dict[str, Any]]) -> None:
        run_id = uuid.uuid4().hex
        run_dir = self.root / "sessions" / self.session_id / "runs"
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": run_id,
            "session_id": self.session_id,
            "query": query,
            "provider": "hive",
            "model_id": "zai-org/glm-5.3-flash",
            "created_at": datetime.now(UTC).isoformat(),
            "events": events,
        }
        target = run_dir / f"{run_id}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        temporary.replace(target)
        self._write_session()

    async def research(self, query: str) -> None:
        print(f"\n\033[36m› research\033[0m {query}")
        if self.orchestrator is None:
            async for _ in self.typed_stream(query):
                pass
            return
        self.history.append(Message(role="user", content=query))
        events: list[dict[str, Any]] = []
        displayed_text = ""
        awaiting_response = False
        produced_report = False
        try:
            async for event in self.orchestrator.execute_query(
                query,
                conversation_history=self.history,
                require_human_approval=True,
                expose_model_stream=False,
            ):
                data = event.model_dump(exclude_none=True)
                events.append(data)
                if data.get("type") == "text_delta":
                    content = str(data.get("content", ""))
                    displayed_text += content
                    print(content, end="", flush=True)
                elif data.get("type") == "status":
                    print(f"\n\033[90m· {data.get('message', '')}\033[0m")
                elif data.get("type") == "tool_status":
                    state = data.get("status", "")
                    marker = "✓" if state == "completed" else "×" if state == "error" else "…"
                    print(f"\n\033[32m{marker}\033[0m {data.get('tool_name')} \033[90m{state}\033[0m")
                elif data.get("type") in {"approval_required", "clarification_required", "manual_review_required"}:
                    awaiting_response = True
                    prompt = data.get("message") or "Review the proposed research step."
                    print(f"\n\033[33m? review required\033[0m\n{prompt}")
                elif data.get("type") == "error":
                    print(f"\n\033[31m× error\033[0m {data.get('message', '')}")
                elif data.get("type") == "final_payload":
                    produced_report = True
                    payload = data.get("payload", {})
                    status = payload.get("status") if isinstance(payload, dict) else None
                    if status == "awaiting_user_input" and not awaiting_response:
                        awaiting_response = True
                        print(f"\n\033[33m? review required\033[0m\n{payload.get('reasoning', 'Review the proposed research step.')}")
                    if awaiting_response:
                        answer = input("\nresponse (approve / revise / cancel) > ").strip()
                        if not answer or answer.lower() == "cancel":
                            print("\033[90mRun paused. No report was approved.\033[0m")
                            self._write_run(query, events)
                            return
                        self.history.append(Message(role="assistant", content=displayed_text))
                        self.history.append(Message(role="user", content=answer))
                        await self.research(answer)
                        return
            label = "run complete" if produced_report else "response complete"
            print(f"\n\033[32m✓ {label}\033[0m")
            self._write_run(query, events)

        except KeyboardInterrupt:
            print("\n\033[90mRun cancelled; prior session data is preserved.\033[0m")
            self._write_run(query, events)
        except Exception as exc:  # noqa: BLE001 - CLI boundary renders a concise failure
            print(f"\n\033[31m× provider/pipeline failure\033[0m {exc}")
            print("\033[90mNo report was approved. Session data is preserved.\033[0m")
            self._write_run(query, events)

    async def typed_stream(self, query: str) -> AsyncIterator[ResearchEvent]:
        """Expose the existing orchestrator through the terminal event boundary."""
        if self.orchestrator is None:
            async for event in self._agent_loop_stream(query):
                yield event
            return
        pending = self.store.read_pending()
        execution_query = query
        if (
            pending
            and pending.get("kind") == "approval"
            and query.casefold().strip() in {"y", "yes", "approve", "approved", "proceed"}
        ):
            execution_query = str(pending.get("query") or query)
        user_message = Message(role="user", content=query)
        self.history.append(user_message)
        self.persistence.append_message(user_message)
        self._compact_history(include_budget=True)
        response_text = ""
        events: list[ResearchEvent] = []
        run_id: str | None = None
        terminal_status = "interrupted"
        try:
            async for event in supervise(
                adapt_legacy_stream(
                    self.orchestrator.execute_query(
                        execution_query,
                        conversation_history=self.history,
                        require_human_approval=self.mode != "autonomous",
                        expose_model_stream=True,
                    ),
                    conversation_id=self.conversation_id,
                    query=query,
                ),
                conversation_id=self.conversation_id,
            ):
                events.append(event)
                self.store.append_trace_event(event)
                run_id = str(event.meta.run_id)
                if event.type == "run.started":
                    self.store.begin_run(query=query, run_id=run_id)
                if event.type == "response.delta":
                    response_text += event.text
                elif event.type == "approval.requested":
                    assistant_message = Message(role="assistant", content=event.prompt)
                    self.history.append(assistant_message)
                    self.persistence.append_message(assistant_message)
                    self.persistence.write_pending(
                        {
                            "kind": "approval",
                            "run_id": run_id,
                            "query": query,
                            "prompt": event.prompt,
                            "details": event.details,
                        }
                    )
                elif event.type == "clarification.requested":
                    assistant_message = Message(role="assistant", content=event.prompt)
                    self.history.append(assistant_message)
                    self.persistence.append_message(assistant_message)
                    self.persistence.write_pending(
                        {
                            "kind": "clarification",
                            "run_id": run_id,
                            "query": query,
                            "prompt": event.prompt,
                        }
                    )
                elif event.type == "run.completed":
                    terminal_status = event.terminal_status
                elif event.type == "run.failed":
                    terminal_status = "failed"
                elif event.type == "run.cancelled":
                    terminal_status = "cancelled"
                yield event
            if terminal_status == "success" and response_text:
                assistant_message = Message(role="assistant", content=response_text)
                self.history.append(assistant_message)
                self.persistence.append_message(assistant_message)
            if terminal_status in {"success", "failed", "cancelled"}:
                self.persistence.clear_pending()
        except asyncio.CancelledError:
            terminal_status = "cancelled"
            raise
        finally:
            if run_id:
                self.persistence.write_run(
                    query=query,
                    run_id=run_id,
                    status=terminal_status,
                    events=[event.model_dump(mode="json") for event in events],
                )

    async def _agent_loop_stream(self, query: str) -> AsyncIterator[ResearchEvent]:
        """Run the production conversational loop; graph remains a compatibility path."""
        pending = self.store.read_pending()
        approved_tool_ids: set[str] = set()
        if pending and pending.get("kind") in {"approval", "clarification"}:
            answer = query.casefold().strip()
            checkpoint = self.store.read_checkpoint() or {}
            raw_messages = checkpoint.get("messages", [])
            self.history = [Message.model_validate(item) for item in raw_messages]
            if pending.get("kind") == "approval" and answer in {
                "y", "yes", "approve", "approved", "proceed"
            }:
                if checkpoint.get("tool_call_id"):
                    approved_tool_ids.add(str(checkpoint["tool_call_id"]))
            elif pending.get("kind") == "approval" and answer in {
                "n", "no", "reject", "cancel"
            }:
                self.persistence.clear_pending()
                cancellation_event = EventFactory(self.conversation_id).make(
                    RunCancelled, reason="request rejected by user"
                )
                yield cancellation_event
                return
            else:
                self.history.append(Message(role="user", content=query))
                self.persistence.append_message(self.history[-1])

        if not pending:
            user_message = Message(role="user", content=query)
            self.history.append(user_message)
            self.persistence.append_message(user_message)
        self._compact_history()

        self.runtime.mode = self.mode
        events: list[ResearchEvent] = []
        response_text: list[str] = []
        status = "interrupted"
        run_id: str | None = None

        def persist_message(message: Message) -> None:
            self.history.append(message)
            self.persistence.append_message(message)

        try:
            async for event in self.runtime.stream(
                self.history,
                query,
                conversation_id=self.conversation_id,
                approved_tool_ids=approved_tool_ids,
                checkpoint_writer=self.persistence.write_checkpoint,
                message_writer=persist_message,
            ):
                events.append(event)
                if diagnostics_enabled():
                    logger.debug(
                        "run event type=%s sequence=%s run_id=%s payload=%s",
                        event.type,
                        event.meta.sequence,
                        event.meta.run_id,
                        diagnostic_payload(event.model_dump(mode="json"))
                        if os.environ.get("FINAI_DIAGNOSTICS") == "payloads"
                        else "omitted",
                    )
                self.store.append_trace_event(event)
                run_id = str(event.meta.run_id)
                if event.type == "run.started":
                    self.store.begin_run(query=query, run_id=run_id)
                elif event.type == "response.delta":
                    response_text.append(event.text)
                elif event.type == "approval.requested":
                    self.persistence.write_pending(
                        {
                            "kind": "approval",
                            "run_id": run_id,
                            "query": query,
                            "prompt": event.prompt,
                            "details": event.details,
                        }
                    )
                    status = "awaiting_approval"
                elif event.type == "run.completed":
                    status = event.terminal_status
                elif event.type == "run.failed":
                    status = "failed"
                elif event.type == "run.cancelled":
                    status = "cancelled"
                yield event
            if response_text and not any(
                message.role == "assistant"
                and message.content == "".join(response_text)
                for message in self.history[-2:]
            ):
                # The runtime already persisted the complete assistant message;
                # deltas only drive the live renderer.
                persist_message(Message(role="assistant", content="".join(response_text)))
            if status in {"success", "failed", "cancelled"}:
                self.persistence.clear_pending()
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception:
            logger.exception("agent loop stream failed session=%s", self.session_id)
            raise
        finally:
            if run_id:
                self.persistence.write_run(
                    query=query,
                    run_id=run_id,
                    status=status,
                    events=[event.model_dump(mode="json") for event in events],
                )

    async def run(self) -> None:
        print("\033[36mFIN-AI\033[0m  interactive research terminal")
        print("Type /help for commands. Analysis is evidence-grounded and human-approved.\n")
        while True:
            try:
                line = input("fin-ai> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not line:
                continue
            if line == "/exit":
                return
            if line == "/help":
                print("\n/research <query>   start a research run\n/status              show session details\n/history             print this session\n/reset               start a new session\n/exit                quit\n")
                continue
            if line == "/status":
                print(f"session={self.session_id} messages={len(self.history)}")
                continue
            if line == "/history":
                for message in self.history:
                    print(f"{message.role}: {message.content}")
                continue
            if line == "/reset":
                self.history.clear()
                self.session_id = uuid.uuid4().hex
                self.store = SessionStore(self.root, self.session_id)
                print(f"new session={self.session_id}")
                continue
            query = line.removeprefix("/research ").strip()
            if query:
                await self.research(query)
            else:
                print("Use /research <question>.")
