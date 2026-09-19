"""Textual interactive terminal for FIN-AI.

The runtime emits typed events. This module owns only their presentation.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from typing import ClassVar

from app.events.models import ResearchEvent
from rich.markup import escape
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Button, Static, TextArea

from .app_dispatch import CommandDispatchMixin
from .app_events import is_activity_event, is_terminal_event, is_tool_event
from .commands import CommandRegistry, parse_command
from .render import (
    FINAI_RICH_THEME,
    render_activity,
    render_context,
    render_header,
    render_response,
    render_sources,
    render_status,
    render_user_message,
)
from .screens import ApprovalScreen
from .session_store import SessionStore
from .state import PresentationPhase, PresentationState, reduce_event
from .theme import CSS_VARIABLES
from .widgets import (
    AppHeader,
    AssistantMessage,
    Composer,
    ContextRail,
    NavigationRail,
    RunActivity,
    UserMessage,
)

WELCOME = """WELCOME TO

FIN-AI

Financial intelligence, grounded in evidence.

Ask about companies, markets, financial statements, technical analysis,
news, sectors, and macroeconomic trends.

YOUR RESEARCH ASSISTANT

Ask about companies, markets, or financial data. I'll research, analyze,
and provide evidence-based insights from trusted sources.

TRY ONE OF THESE EXAMPLES

→ Analyse HDFC Bank for the last 1 year
→ Summarize TCS's latest quarterly results
→ Compare Reliance vs Infosys fundamentals
→ Analyse the Indian banking sector outlook
→ Latest news affecting IT stocks
→ Calculate HDFC Bank key ratios

CAPABILITIES

Stock & Market Data  ·  Fundamental Analysis  ·  Technical Analysis
News & Sentiment      ·  Research & Reports"""


class FinAIApp(CommandDispatchMixin, App[None]):
    """Terminal application; domain code remains outside the UI."""

    TITLE = "FIN-AI"
    SUB_TITLE = "Financial Intelligence & Research"
    CSS_PATH: ClassVar[list[str | object]] = [  # type: ignore[assignment]
        "styles/tokens.tcss",
        "styles/layout.tcss",
        "styles/components.tcss",
    ]
    BINDINGS: ClassVar[list[tuple[str, str] | tuple[str, str, str]]] = [  # type: ignore[assignment]
        ("ctrl+n", "new_research", "New research"),
        ("ctrl+k", "sessions", "Sessions"),
        ("ctrl+b", "toggle_sidebar", "Toggle sidebar"),
        ("ctrl+e", "export", "Export"),
        ("ctrl+c", "cancel_or_exit", "Cancel / Exit"),
        ("ctrl+shift+c", "copy_text", "Copy selection"),
        ("escape", "cancel_run", "Cancel"),
        ("ctrl+z", "quit_app", "Exit"),
        ("ctrl+l", "clear_screen", "Clear"),
    ]

    def __init__(
        self,
        event_stream: Callable[[str], AsyncIterator[ResearchEvent]] | None = None,
        *,
        session_store: SessionStore | None = None,
        compact_callback: Callable[[], dict[str, int | str]] | None = None,
        session_callback: Callable[[str], None] | None = None,
        new_session_callback: Callable[[], None] | None = None,
        clear_pending_callback: Callable[[], None] | None = None,
        mode: str = "guided",
    ) -> None:
        super().__init__()
        self.event_stream = event_stream
        self.session_store = session_store
        self.compact_callback = compact_callback
        self.session_callback = session_callback
        self.new_session_callback = new_session_callback
        self.clear_pending_callback = clear_pending_callback
        self.mode = mode
        self.state = PresentationState()
        self.registry = CommandRegistry.default()
        self._run_task: asyncio.Task[None] | None = None
        self._spinner_index = 0
        self._response_widget: AssistantMessage | None = None
        self._activity_widget: RunActivity | None = None
        self._run_started_at: float | None = None
        self._event_log: list[str] = []
        self._command_selection = 0
        self._queued_prompts: list[str] = []

    def compose(self) -> ComposeResult:
        yield AppHeader(id="topbar")
        with Horizontal(id="workspace"):
            yield NavigationRail(
                id="navigation",
            )
            yield VerticalScroll(Static(WELCOME, id="welcome"), id="conversation")
            yield ContextRail(id="context-rail")
        yield Static("FIN-AI · ready", id="status")
        with Horizontal(id="composer-row"):
            yield Composer(placeholder="Ask FIN-AI...", id="composer")
            yield Button("Send", variant="primary", id="send")
        yield Static(
            "[Attach]  [Web Search]  [Deep Research]    /context  /sources  /trace",
            id="composer-tools",
        )
        yield Static("", id="command-menu")
        yield Static(
            "Enter send · Shift+Enter newline · / commands · Esc cancel · ? help",
            id="hints",
        )

    def get_theme_variable_defaults(self) -> dict[str, str]:
        return CSS_VARIABLES

    def on_mount(self) -> None:
        self.console.push_theme(FINAI_RICH_THEME)
        self._apply_layout(self.size.width)
        self._refresh_chrome()
        self.query_one("#composer", Composer).focus()
        self.set_interval(0.2, self._tick_activity)

    async def action_new_research(self) -> None:
        await self._command("new", [])

    async def action_sessions(self) -> None:
        await self._command("sessions", [])

    def action_toggle_sidebar(self) -> None:
        self.query_one("#navigation").display = not self.query_one(
            "#navigation"
        ).display

    async def action_export(self) -> None:
        await self._command("logs", [])

    def on_resize(self, event: events.Resize) -> None:
        self._apply_layout(event.size.width)

    def _apply_layout(self, width: int) -> None:
        layout = (
            "layout-wide"
            if width >= 140
            else "layout-medium"
            if width >= 120
            else "layout-compact"
            if width >= 90
            else "layout-narrow"
        )
        self.screen.remove_class(
            "layout-wide", "layout-medium", "layout-compact", "layout-narrow"
        )
        self.screen.add_class(layout)

    def _refresh_chrome(self) -> None:
        session_id = self.session_store.session_id if self.session_store else None
        self.query_one("#topbar", AppHeader).update(
            render_header(self.state, mode=self.mode, session_id=session_id)
        )
        self.query_one("#context-rail", ContextRail).update(
            render_context(self.state, mode=self.mode, session_id=session_id)
        )

    def _tick_activity(self) -> None:
        if not self._run_task or self._run_task.done():
            return
        self._spinner_index = (self._spinner_index + 1) % 4
        spinner = ("◉", "◌", "○", "◌")[self._spinner_index]
        elapsed_s = (
            time.monotonic() - self._run_started_at if self._run_started_at else None
        )
        try:
            self.query_one("#status", Static).update(
                render_status(self.state, spinner=spinner, elapsed_s=elapsed_s)
            )
            self._refresh_chrome()
        except NoMatches:
            # Textual may tick once while its test/runtime screen is unmounting.
            return

    def on_text_area_changed(self, message: TextArea.Changed) -> None:
        if message.text_area.id == "composer":
            self._update_command_menu(message.text_area.text)

    def _update_command_menu(self, raw_value: str) -> None:
        menu = self.query_one("#command-menu", Static)
        value = raw_value.strip()
        if not value.startswith("/") or " " in value:
            menu.remove_class("visible")
            return
        matches = self.registry.suggestion_items(value[1:])
        if not matches:
            menu.remove_class("visible")
            return
        self._command_selection = min(self._command_selection, len(matches) - 1)
        lines = ["Commands"]
        for index, command in enumerate(matches):
            marker = "›" if index == self._command_selection else " "
            lines.append(f"  {marker} /{command.name:<10} {command.description}")
        menu.update("\n".join(lines))
        menu.add_class("visible")

    async def on_composer_submitted(self, message: Composer.Submitted) -> None:
        query = message.value.strip()
        message.composer.text = ""
        self.query_one("#command-menu", Static).remove_class("visible")
        if not query:
            return
        name, args = parse_command(query)
        if name:
            await self._command(name, args)
            return
        if self._run_task and not self._run_task.done():
            self._queued_prompts.append(query)
            self._mount_user(query)
            await self._mount(
                Static(
                    "Queued · will run after the current request", classes="activity"
                )
            )
            return
        if self.state.phase is PresentationPhase.WAITING_FOR_APPROVAL:
            decision = query.casefold()
            if decision in {"d", "details"}:
                await self._command("debug", [])
            elif decision in {"n", "no", "reject", "rejected", "cancel"}:
                self._reject_pending()
            elif decision in {"y", "yes", "approve", "approved", "proceed"}:
                self._approval_result(True)
            else:
                await self._mount(
                    Static("Approval required · choose approve, reject, or details")
                )
            return
        if self.state.phase is PresentationPhase.WAITING_FOR_CLARIFICATION:
            self._mount_user(query)
            self._start_run(query)
            return
        self._mount_user(query)
        self._start_run(query)

    async def on_button_pressed(self, message: Button.Pressed) -> None:
        if message.button.id == "nav-new":
            await self._command("new", [])
            return
        if message.button.id == "nav-sessions":
            await self._command("sessions", [])
            return
        if message.button.id == "nav-trace":
            await self._command("trace", [])
            return
        if message.button.id != "send":
            return
        composer = self.query_one("#composer", Composer)
        self.post_message(Composer.Submitted(composer, composer.text))

    def on_key(self, event) -> None:
        if event.key not in {"up", "down", "tab"}:
            return
        composer = self.query_one("#composer", Composer)
        value = composer.text.strip()
        if not value.startswith("/") or " " in value:
            return
        matches = self.registry.suggestion_items(value[1:])
        if not matches:
            return
        event.stop()
        if event.key == "up":
            self._command_selection = (self._command_selection - 1) % len(matches)
        elif event.key == "down":
            self._command_selection = (self._command_selection + 1) % len(matches)
        else:
            composer.text = "/" + matches[self._command_selection].name + " "
            composer.move_cursor((0, len(composer.text)))
        self._update_command_menu(composer.text)

    def _mount_user(self, query: str) -> None:
        for welcome in self.query("#welcome"):
            welcome.display = False
        self.query_one("#conversation", VerticalScroll).mount(
            UserMessage(render_user_message(query), classes="message user-message")
        )

    async def _mount(self, widget: Static) -> None:
        await self.query_one("#conversation", VerticalScroll).mount(widget)

    def _start_run(self, query: str) -> None:
        self.state = PresentationState(phase=PresentationPhase.STARTING)
        self._run_started_at = time.monotonic()
        self._event_log = []
        self._response_widget = None
        self._activity_widget = RunActivity(
            "◉ Preparing research...", classes="run-activity activity"
        )
        self.query_one("#conversation", VerticalScroll).mount(self._activity_widget)
        self.query_one("#status", Static).update("◉ FIN-AI · preparing research...")
        self._refresh_chrome()
        if self.event_stream:
            self._run_task = asyncio.create_task(
                self._consume(self.event_stream(query))
            )

    async def _consume(self, events: AsyncIterator[ResearchEvent]) -> None:
        conversation = self.query_one("#conversation", VerticalScroll)
        try:
            async for event in events:
                self._event_log.append(f"#{event.meta.sequence} {event.type}")
                self.state = reduce_event(self.state, event)
                self._refresh_chrome()
                if event.type == "response.delta":
                    if self._response_widget is None:
                        self._response_widget = AssistantMessage(
                            classes="message assistant-message"
                        )
                        await conversation.mount(self._response_widget)
                    self._response_widget.update(
                        render_response(self.state, streaming=True)
                    )
                elif is_activity_event(event.type):
                    if self._activity_widget is not None:
                        if is_tool_event(event.type):
                            self._activity_widget.add_class("tool-event")
                        elif event.type in {"tool.completed", "sources.updated"}:
                            self._activity_widget.remove_class("tool-event")
                            self._activity_widget.add_class("result-event")
                    if (
                        is_terminal_event(event.type)
                        and self._activity_widget is not None
                    ):
                        self._activity_widget.display = False
                    if self._activity_widget is not None:
                        self._activity_widget.update(render_activity(self.state))
                    if (
                        event.type == "run.completed"
                        and self._response_widget is not None
                    ):
                        self._response_widget.update(render_response(self.state))
                    if event.type == "run.completed" and event.artifact_path:
                        await conversation.mount(
                            Static(
                                f"Run artifact: {escape(event.artifact_path)}",
                                classes="activity",
                            )
                        )
                elif event.type == "approval.requested":
                    self.push_screen(
                        ApprovalScreen(event.prompt, event.details),
                        self._approval_result,
                    )
                    if self._activity_widget is not None:
                        self._activity_widget.update(render_activity(self.state))
                elif event.type == "clarification.requested":
                    await conversation.mount(
                        AssistantMessage(
                            f"FIN-AI\n\nNeeds clarification\n{escape(event.prompt)}",
                            classes="message assistant-message",
                        )
                    )
                elif event.type == "sources.updated":
                    await conversation.mount(
                        Static(
                            render_sources(self.state.sources),
                            classes="sources-message",
                        )
                    )
                elapsed_s = (
                    time.monotonic() - self._run_started_at
                    if self._run_started_at
                    else None
                )
                self.query_one("#status", Static).update(
                    render_status(self.state, elapsed_s=elapsed_s)
                )
                self._refresh_chrome()
                conversation.scroll_end(animate=False)
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            self.state = PresentationState(
                phase=PresentationPhase.CANCELLED,
                query=self.state.query,
                run_id=self.state.run_id,
                response_text=self.state.response_text,
            )
            if self.is_attached:
                self.query_one("#status", Static).update("FIN-AI · cancelled")
                self._refresh_chrome()
            if self._activity_widget is not None and self._activity_widget.is_attached:
                self._activity_widget.update(render_activity(self.state))
        except Exception as exc:  # noqa: BLE001 - UI boundary must remain usable
            if self.is_attached:
                await conversation.mount(
                    Static(
                        f"✗ FIN-AI stopped unexpectedly\n\n  {escape(str(exc))}\n\n  /debug for the full local trace",
                        classes="message error",
                    )
                )
                self.query_one("#status", Static).update("FIN-AI · failed")
                self._refresh_chrome()
        if (
            self._queued_prompts
            and self.state.phase is not PresentationPhase.CANCELLING
        ):
            next_query = self._queued_prompts.pop(0)
            self._start_run(next_query)

    def _approval_result(self, approved: bool | None) -> None:
        if self.session_store and self.state.run_id:
            self.session_store.trace.append_raw(
                event_type="approval.resolved",
                run_id=str(self.state.run_id),
                conversation_id=self.session_store.session_id,
                payload={"decision": "approved" if approved else "rejected"},
            )
        if approved:
            # The stream adapter uses an explicit approval response to resume
            # the pending plan. Resubmitting the original query reopens the
            # approval gate indefinitely.
            self._start_run("yes")
            return
        self._reject_pending()

    def _reject_pending(self) -> None:
        if self.clear_pending_callback:
            self.clear_pending_callback()
        self.state = PresentationState()
        self.query_one("#status", Static).update("FIN-AI · ready")
        self.query_one("#conversation", VerticalScroll).mount(
            Static("✓ Approval rejected", classes="activity")
        )

    def action_cancel_run(self) -> None:
        if self._run_task and not self._run_task.done():
            self.state = PresentationState(
                phase=PresentationPhase.CANCELLING,
                run_id=self.state.run_id,
                query=self.state.query,
                response_text=self.state.response_text,
            )
            self.query_one("#status", Static).update("FIN-AI · cancelling...")
            self._run_task.cancel()

    def action_cancel_or_exit(self) -> None:
        if self._run_task and not self._run_task.done():
            self.action_cancel_run()
        else:
            self.exit()

    def action_quit_app(self) -> None:
        self.action_cancel_or_exit()

    async def action_clear_screen(self) -> None:
        conversation = self.query_one("#conversation", VerticalScroll)
        await conversation.remove_children()
        await conversation.mount(Static(WELCOME, id="welcome"))
