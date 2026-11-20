"""Command dispatch for the FIN-AI terminal."""

from __future__ import annotations

from typing import Any

from app.config import settings
from rich.markup import escape
from textual.containers import VerticalScroll
from textual.widgets import Static

from .app_commands import (
    context_text,
    mode_error_text,
    queries_text,
    status_text,
    trace_text,
)
from .context_budget import ContextBudget
from .render import (
    FinMarkdown,
    render_command,
    render_debug,
    render_sources,
    render_user_message,
)
from .safety import sanitize_terminal_text
from .screens import SessionScreen
from .session_store import SessionStore
from .state import PresentationState
from .widgets import AssistantMessage, CommandMessage, UserMessage

MODES = ("guided", "review", "autonomous")


class CommandDispatchMixin:
    query_one: Any
    registry: Any
    new_session_callback: Any
    _event_log: Any
    session_store: Any
    mode: Any
    state: Any
    _response_widget: Any
    _activity_widget: Any
    exit: Any
    compact_callback: Any
    session_callback: Any
    push_screen: Any
    _run_task: Any
    _last_artifact: str | None
    _last_query: str | None
    _mount_user: Any
    _start_run: Any
    _refresh_chrome: Any
    _refresh_sessions: Any

    async def _note(self, text: str, classes: str = "activity") -> None:
        conversation = self.query_one("#conversation", VerticalScroll)
        marker = "✗" if classes == "error" else "⎿"
        await conversation.mount(Static(f"  {marker} {escape(text)}", classes=classes))

    async def _show_sessions(self) -> None:
        root = self.session_store.root if self.session_store else None
        sessions = SessionStore.list_sessions(root) if root else []
        self.push_screen(SessionScreen(sessions), self._on_session_picked)

    async def _on_session_picked(self, session_id: str | None) -> None:
        if session_id:
            await self._resume(session_id)

    async def _resume(self, session_id: str) -> None:
        """Switch the runtime to a saved session and rebuild the visible view."""
        if self.session_callback is None:
            await self._note("Session switching is unavailable.", "error")
            return
        if self._run_task and not self._run_task.done():
            await self._note("A request is running; cancel it before switching.")
            return
        self.session_callback(session_id)
        conversation = self.query_one("#conversation", VerticalScroll)
        await conversation.remove_children()
        self.state = PresentationState()
        self._response_widget = None
        self._activity_widget = None
        self._last_query = None
        self._last_artifact = None
        history = self.session_store.load_history() if self.session_store else []
        for message in history:
            if message.role == "user":
                self._last_query = message.content
                await conversation.mount(
                    UserMessage(
                        render_user_message(message.content),
                        classes="message user-message",
                    )
                )
            elif message.role == "assistant":
                await conversation.mount(
                    AssistantMessage(
                        FinMarkdown(sanitize_terminal_text(message.content)),
                        classes="message assistant-message",
                    )
                )
        await self._note(f"Resumed session {session_id[:8]} · {len(history)} messages")
        self._refresh_chrome()
        self._refresh_sessions()

    async def _resume_by_prefix(self, prefix: str) -> None:
        root = self.session_store.root if self.session_store else None
        matches = [
            session["id"]
            for session in (SessionStore.list_sessions(root) if root else [])
            if session["id"].startswith(prefix)
        ]
        if len(matches) == 1:
            await self._resume(matches[0])
        elif matches:
            await self._note(f"Ambiguous session prefix '{prefix}'.", "error")
        else:
            await self._note(f"No session matches '{prefix}'. Try /sessions.", "error")

    def _last_user_query(self) -> str | None:
        if self._last_query:
            return str(self._last_query)
        if self.session_store:
            for message in reversed(self.session_store.load_history()):
                if message.role == "user":
                    return str(message.content)
        return None

    async def _command(self, name: str, args: list[str]) -> None:
        conversation = self.query_one("#conversation", VerticalScroll)
        await conversation.mount(
            CommandMessage(render_command(name, args), classes="command-message")
        )
        if name == "help":
            await conversation.mount(
                Static(self.registry.help_text(), classes="trace-panel")
            )
        elif name in {"clear", "new"}:
            await conversation.remove_children()
            self.state = PresentationState()
            self._response_widget = None
            self._activity_widget = None
            self._last_query = None
            self._last_artifact = None
            if name == "new" and self.new_session_callback:
                self.new_session_callback()
                self._refresh_chrome()
                self._refresh_sessions()
        elif name == "status":
            await conversation.mount(
                Static(status_text(self.state), classes="trace-panel")
            )
        elif name == "debug":
            await conversation.mount(
                Static(render_debug(self.state, self._event_log), classes="trace-panel")
            )
        elif name == "sources":
            await conversation.mount(
                Static(render_sources(self.state.sources), classes="sources-message")
            )
        elif name == "trace":
            records = self.session_store.trace.read() if self.session_store else []
            await conversation.mount(
                Static(
                    trace_text(records, self.session_store.trace.path)
                    if self.session_store
                    else "\nTrace is unavailable.",
                    classes="trace-panel",
                )
            )
        elif name == "artifact":
            await self._note(
                f"Run artifact · {self._last_artifact}"
                if self._last_artifact
                else "No run artifact yet."
            )
        elif name == "logs":
            await conversation.mount(
                Static(
                    "Run artifacts: .finai/sessions/<session>/runs/",
                    classes="trace-panel",
                )
            )
        elif name == "mode":
            if not args:
                await self._note(f"Mode · {self.mode}")
            elif args[0] in MODES:
                self.mode = args[0]
                self._refresh_chrome()
                await self._note(f"Mode · {self.mode}")
            else:
                await self._note(mode_error_text(args[0], MODES), "error")
        elif name == "history":
            queries = [
                message.content
                for message in (
                    self.session_store.load_history() if self.session_store else []
                )
                if message.role == "user"
            ]
            await self._note(queries_text(queries))
        elif name == "retry":
            query = self._last_user_query()
            if query is None:
                await self._note("Nothing to retry yet.")
            elif self._run_task and not self._run_task.done():
                await self._note("A request is already running.")
            else:
                self._mount_user(query)
                self._start_run(query)
        elif name == "context":
            budget = ContextBudget(
                max_tokens=settings.FINAI_CONTEXT_MAX_TOKENS,
                compaction_ratio=settings.FINAI_CONTEXT_COMPACTION_RATIO,
            )
            history = self.session_store.load_history() if self.session_store else []
            estimated = int(budget.compact(history)[1]["estimated_tokens"])
            stored = self.session_store.read_context() if self.session_store else {}
            await self._note(context_text(len(history), estimated, budget, stored))
        elif name == "compact":
            if self.compact_callback is None:
                await self._note("Compaction is unavailable in this session.")
            else:
                result = self.compact_callback()
                moved = int(result.get("compacted_messages", 0))
                await self._note(
                    f"Compacted {moved} older messages."
                    if moved
                    else "Nothing to compact; the conversation is under the "
                    f"compaction limit (~{result.get('estimated_tokens', 0)} tokens)."
                )
        elif name == "sessions":
            await self._show_sessions()
        elif name == "resume":
            if not args:
                await self._note("Usage: /resume <session-id-prefix>", "error")
            else:
                await self._resume_by_prefix(args[0])
        elif name == "exit":
            self.exit()
        else:
            await self._note(f"Unknown command /{name} — try /help", "error")
