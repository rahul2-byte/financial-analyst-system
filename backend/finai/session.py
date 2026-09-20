"""Conversation state, runtime streaming, and local persistence."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from app.config import settings
from app.core.diagnostics import diagnostic_payload, diagnostics_enabled
from app.core.resources import build_runtime_resources
from app.events.models import ResearchEvent
from app.models.request_models import Message
from app.observability.provider_archive import ProviderArchive

from .context_budget import ContextBudget
from .session_persistence import SessionPersistence
from .session_runtime import ResearchRunner
from .session_store import SessionStore

logger = logging.getLogger(__name__)


class FinAIRepl:
    def __init__(
        self,
        root: Path | None = None,
        session_id: str | None = None,
        replay_snapshots: dict[str, str] | None = None,
    ) -> None:
        self.root = root or Path(".finai")
        self.session_id = session_id or uuid.uuid4().hex
        self.store = SessionStore(self.root, self.session_id)
        self.persistence = SessionPersistence(self.store)
        self.mode = "guided"
        self.history: list[Message] = []
        self._load_session()
        self.resources = build_runtime_resources(
            llm_service=None,
            provider_archive=ProviderArchive(self.root),
            replay_snapshots=replay_snapshots,
        )
        self.hive_service = self.resources.llm_service
        self.runtime = ResearchRunner(
            self.resources,
            self.mode,
        )

    @property
    def conversation_id(self) -> uuid.UUID:
        try:
            return uuid.UUID(self.session_id)
        except ValueError:
            return uuid.uuid5(uuid.NAMESPACE_URL, f"finai:{self.session_id}")

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

    async def research(self, query: str) -> None:
        print(f"\n\033[36m› research\033[0m {query}")
        terminal_status = "interrupted"
        try:
            async for event in self.typed_stream(query):
                if event.type == "response.delta":
                    print(event.text, end="", flush=True)
                elif event.type == "clarification.requested":
                    print(f"\n\033[33m? input required\033[0m\n{event.prompt}")
                    terminal_status = "clarification"
                elif event.type == "run.completed":
                    terminal_status = event.terminal_status
                    if event.artifact_path:
                        print(f"\nRun artifact: {event.artifact_path}")
                elif event.type == "run.failed":
                    terminal_status = "failed"
                    print(
                        f"\n\033[31m× provider/pipeline failure\033[0m {event.message}"
                    )
            if terminal_status not in {"failed", "clarification", "interrupted"}:
                print(f"\n✓ {terminal_status.replace('_', ' ')}")
        except Exception as exc:  # noqa: BLE001 - CLI boundary renders a concise failure
            print(f"\n\033[31m× provider/pipeline failure\033[0m {exc}")
            print("\033[90mSession data is preserved for inspection.\033[0m")

    async def typed_stream(self, query: str) -> AsyncIterator[ResearchEvent]:
        """Run the supported AgentLoop through the terminal event boundary."""
        async for event in self._agent_loop_stream(query):
            yield event

    async def _agent_loop_stream(self, query: str) -> AsyncIterator[ResearchEvent]:
        """Run the production conversational loop."""
        pending = self.store.read_pending()
        if pending and pending.get("kind") == "approval":
            self.persistence.clear_pending()
            pending = None
        if pending and pending.get("kind") == "clarification":
            checkpoint = self.store.read_checkpoint() or {}
            raw_messages = checkpoint.get("messages", [])
            self.history = [Message.model_validate(item) for item in raw_messages]
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
        persisted_final_response = False

        def persist_message(message: Message) -> None:
            nonlocal persisted_final_response
            self.history.append(message)
            self.persistence.append_message(message)
            if message.role == "assistant" and not message.tool_calls:
                persisted_final_response = True

        try:
            async for event in self.runtime.stream(
                self.history,
                query,
                conversation_id=self.conversation_id,
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
                    event = event.model_copy(
                        update={
                            "artifact_path": str(
                                self.store.session_dir / "runs" / f"{run_id}.json"
                            )
                        }
                    )
                    events[-1] = event
                elif event.type == "run.failed":
                    status = "failed"
                elif event.type == "run.cancelled":
                    status = "cancelled"
                yield event
            if response_text and not persisted_final_response:
                # The runtime already persisted the complete assistant message;
                # deltas only drive the live renderer.
                persist_message(
                    Message(role="assistant", content="".join(response_text))
                )
            if status in {
                "success",
                "partial",
                "insufficient_data",
                "completed",
                "completed_with_limited_evidence",
                "failed",
                "cancelled",
            }:
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
        print(
            "Type /help for commands. Analysis is evidence-grounded and human-approved.\n"
        )
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
                print(
                    "\n/research <query>   start a research run\n/status              show session details\n/history             print this session\n/reset               start a new session\n/exit                quit\n"
                )
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
