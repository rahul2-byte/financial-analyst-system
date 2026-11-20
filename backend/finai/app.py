"""Textual interactive terminal for FIN-AI.

The runtime emits typed events. This module owns only their presentation.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from typing import ClassVar

from app.config import settings
from app.events.models import ResearchEvent
from rich.markup import escape
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.timer import Timer
from textual.widgets import Button, Static, TextArea

from .app_dispatch import CommandDispatchMixin
from .app_events import is_activity_event, is_terminal_event
from .commands import CommandRegistry, parse_command
from .plain import friendly_error
from .render import (
    FINAI_RICH_THEME,
    SPINNER_FRAMES,
    has_tool_trail,
    instrument_from_sources,
    render_activity,
    render_clarification,
    render_context,
    render_footer,
    render_header,
    render_hints,
    render_response,
    render_saved_report,
    render_sources,
    render_user_message,
    render_welcome,
)
from .safety import sanitize_terminal_text
from .screens import ApprovalScreen, HelpScreen
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

# Streaming markdown is re-parsed on every render, so deltas are coalesced.
RENDER_INTERVAL_S = 0.08
SCROLL_BOTTOM_TOLERANCE = 3


class RunFinished(Message):
    """Posted when a run task ends so the message loop can start queued work."""

    def __init__(self, task: asyncio.Task[None] | None) -> None:
        super().__init__()
        self.task = task


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
        ("f2", "toggle_context", "Toggle context panel"),
        ("ctrl+o", "toggle_trail", "Expand evidence trail"),
        ("ctrl+e", "export", "Export"),
        ("ctrl+c", "cancel_or_exit", "Cancel / Exit"),
        ("ctrl+shift+c", "copy_text", "Copy selection"),
        ("escape", "cancel_run", "Cancel"),
        ("ctrl+z", "quit_app", "Exit"),
        ("ctrl+l", "clear_screen", "Clear"),
        ("f1", "help", "Help"),
        ("question_mark", "help", "Help"),
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
        self._clarified = False
        self._last_artifact: str | None = None
        self._activity_widget: RunActivity | None = None
        self._trail_expanded = False
        self._run_started_at: float | None = None
        self._event_log: list[str] = []
        self._command_selection = 0
        self._queued_prompts: list[str] = []
        self._last_query: str | None = None
        self._follow_bottom = True
        self._delta_dirty = False
        self._delta_timer: Timer | None = None
        self._last_delta_render = 0.0
        self.response_render_count = 0

    def compose(self) -> ComposeResult:
        yield AppHeader(id="topbar")
        with Horizontal(id="workspace"):
            yield NavigationRail(
                id="navigation",
            )
            yield VerticalScroll(
                Static(render_welcome(), id="welcome"), id="conversation"
            )
            yield ContextRail(id="context-rail")
        yield Static("", id="command-menu")
        with Horizontal(id="composer-row"):
            yield Composer(placeholder="Ask FIN-AI…", id="composer")
            yield Button("Send", variant="primary", id="send")
        yield Static("", id="status")

    def get_theme_variable_defaults(self) -> dict[str, str]:
        return CSS_VARIABLES

    def on_mount(self) -> None:
        self.console.push_theme(FINAI_RICH_THEME)
        self._apply_layout(self.size.width)
        self._refresh_chrome()
        self._refresh_sessions()
        self.query_one("#composer", Composer).focus()
        self.set_interval(0.2, self._tick_activity)

    async def action_new_research(self) -> None:
        await self._command("new", [])

    async def action_sessions(self) -> None:
        await self._command("sessions", [])

    def action_help(self) -> None:
        if not isinstance(self.screen, HelpScreen):
            self.push_screen(HelpScreen(self.registry.help_text(), self.BINDINGS))

    def _refresh_sessions(self) -> None:
        root = self.session_store.root if self.session_store else None
        active = self.session_store.session_id if self.session_store else None
        sessions = SessionStore.list_sessions(root) if root else []
        self.query_one("#navigation", NavigationRail).show_sessions(sessions, active)

    def action_toggle_trail(self) -> None:
        """Expand or collapse the latest answer's evidence trail."""
        self._trail_expanded = not self._trail_expanded
        self._render_trail()

    def action_toggle_context(self) -> None:
        self.query_one("#context-rail").toggle_class("visible")

    def action_toggle_sidebar(self) -> None:
        self.query_one("#navigation").display = not self.query_one(
            "#navigation"
        ).display

    async def action_export(self) -> None:
        await self._command("logs", [])

    def on_resize(self, event: events.Resize) -> None:
        self._apply_layout(event.size.width)
        self._refresh_chrome()

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
            render_header(
                self.state,
                instrument=instrument_from_sources(self.state.sources),
                width=self.size.width - 2,
            )
        )
        model = settings.OPENROUTER_MODEL.rsplit("/", 1)[-1]
        self.query_one("#status", Static).update(
            render_hints(
                mode=self.mode,
                model=model,
                session_id=session_id,
                width=self.size.width - 6,
            )
        )
        self.query_one("#context-rail", ContextRail).update(
            render_context(self.state, mode=self.mode, session_id=session_id)
        )

    def _render_trail(self) -> None:
        """Re-render the run's single activity line group in place."""
        widget = self._activity_widget
        if widget is None or not widget.is_attached:
            return
        running = bool(self._run_task and not self._run_task.done())
        elapsed_s = (
            time.monotonic() - self._run_started_at if self._run_started_at else None
        )
        widget.update(
            render_activity(
                self.state,
                spinner=SPINNER_FRAMES[self._spinner_index] if running else None,
                elapsed_s=elapsed_s if running else None,
                expanded=self._trail_expanded,
            )
        )

    def _tick_activity(self) -> None:
        if not self._run_task or self._run_task.done():
            return
        self._spinner_index = (self._spinner_index + 1) % len(SPINNER_FRAMES)
        self._render_trail()

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
                    "  ⎿ Queued · will run after the current request",
                    classes="activity",
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
        if message.button.id == "nav-reports":
            conversation = self.query_one("#conversation", VerticalScroll)
            if self.session_store is None:
                await conversation.mount(
                    Static("  ⎿ No saved report is available.", classes="activity")
                )
                return
            report = SessionStore.latest_saved_report(self.session_store.root)
            if report is None:
                await conversation.mount(
                    Static("  ⎿ No saved report is available.", classes="activity")
                )
                return
            await conversation.mount(
                AssistantMessage(
                    render_saved_report(report), classes="message assistant-message"
                )
            )
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
        self._last_query = query
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
        self._clarified = False
        self._trail_expanded = False
        self._delta_dirty = False
        self._activity_widget = RunActivity("", classes="run-activity activity")
        self.query_one("#conversation", VerticalScroll).mount(self._activity_widget)
        self._refresh_chrome()
        if self.event_stream:
            self._run_task = asyncio.create_task(
                self._consume(self.event_stream(query), self._activity_widget)
            )
        self._render_trail()

    def _at_bottom(self, conversation: VerticalScroll) -> bool:
        return (
            conversation.scroll_y >= conversation.max_scroll_y - SCROLL_BOTTOM_TOLERANCE
        )

    def _flush_response(self) -> None:
        """Render the accumulated response once and clear the dirty flag."""
        if self._delta_timer is not None:
            self._delta_timer.stop()
            self._delta_timer = None
        widget = self._response_widget
        if not self._delta_dirty or widget is None or not widget.is_attached:
            self._delta_dirty = False
            return
        self._delta_dirty = False
        self._last_delta_render = time.monotonic()
        self.response_render_count += 1
        widget.update(render_response(self.state))
        conversation = self.query_one("#conversation", VerticalScroll)
        if self._follow_bottom:
            conversation.scroll_end(animate=False)

    def _schedule_response_render(self) -> None:
        self._delta_dirty = True
        if self._delta_timer is not None:
            return
        wait = RENDER_INTERVAL_S - (time.monotonic() - self._last_delta_render)
        if wait <= 0:
            self._flush_response()
        else:
            self._delta_timer = self.set_timer(wait, self._flush_response)

    async def on_run_finished(self, message: RunFinished) -> None:
        if self._run_task is message.task:
            self._run_task = None
        if self._run_task is None and self._queued_prompts:
            self._start_run(self._queued_prompts.pop(0))

    async def _ensure_response_widget(
        self, conversation: VerticalScroll
    ) -> AssistantMessage:
        if self._response_widget is None:
            self._response_widget = AssistantMessage(
                classes="message assistant-message"
            )
            await conversation.mount(self._response_widget)
        return self._response_widget

    async def _finish_run(
        self, event: ResearchEvent, conversation: VerticalScroll
    ) -> None:
        """Close one run: final answer, one sources block, one footer line."""
        self._delta_dirty = False
        if self._delta_timer is not None:
            self._delta_timer.stop()
            self._delta_timer = None
        if self.state.response_text and not self._clarified:
            widget = await self._ensure_response_widget(conversation)
            widget.update(render_response(self.state))
        if self._activity_widget is not None:
            self._render_trail()
            if not has_tool_trail(self.state):
                self._activity_widget.display = False
        duration_ms = getattr(event, "duration_ms", None)
        elapsed_s = (
            duration_ms / 1000
            if duration_ms
            else time.monotonic() - self._run_started_at
            if self._run_started_at
            else None
        )
        if event.type == "run.completed":
            self._last_artifact = getattr(event, "artifact_path", None)
        if self._clarified:
            return
        if event.type == "run.failed" and self.state.error:
            await conversation.mount(
                Static(
                    "✗ "
                    + escape(sanitize_terminal_text(friendly_error(self.state.error))),
                    classes="error",
                )
            )
        if self.state.sources:
            await conversation.mount(
                Static(render_sources(self.state.sources), classes="sources-message")
            )
        chat_only = (
            not has_tool_trail(self.state)
            and not self.state.sources
            and event.type != "run.failed"
            and self.state.phase.value != "failed"
        )
        if chat_only:
            return
        await conversation.mount(
            Static(render_footer(self.state, elapsed_s=elapsed_s), classes="run-footer")
        )

    async def _consume(
        self, events: AsyncIterator[ResearchEvent], activity: RunActivity | None
    ) -> None:
        conversation = self.query_one("#conversation", VerticalScroll)
        task = asyncio.current_task()
        self._follow_bottom = True
        try:
            async for event in events:
                self._follow_bottom = self._at_bottom(conversation)
                self._event_log.append(f"#{event.meta.sequence} {event.type}")
                self.state = reduce_event(self.state, event)
                self._refresh_chrome()
                if event.type == "response.delta":
                    await self._ensure_response_widget(conversation)
                    self._schedule_response_render()
                elif is_activity_event(event.type):
                    self._render_trail()
                    if is_terminal_event(event.type):
                        await self._finish_run(event, conversation)
                elif event.type == "approval.requested":
                    self.push_screen(
                        ApprovalScreen(event.prompt, event.details),
                        self._approval_result,
                    )
                    self._render_trail()
                elif event.type == "clarification.requested":
                    self._clarified = True
                    await conversation.mount(
                        AssistantMessage(
                            render_clarification(event.prompt),
                            classes="message assistant-message",
                        )
                    )
                if self._follow_bottom:
                    conversation.scroll_end(animate=False)
        except asyncio.CancelledError:
            self.state = PresentationState(
                phase=PresentationPhase.CANCELLED,
                query=self.state.query,
                run_id=self.state.run_id,
                response_text=self.state.response_text,
                activities=self.state.activities,
                sources=self.state.sources,
                terminal_status="cancelled",
            )
            if self.is_attached:
                self._refresh_chrome()
            self._flush_response()
            if activity is not None and not self.state.activities:
                activity.display = False
            if self.is_attached:
                self._render_trail()
                conversation.mount(
                    Static("· Cancelled", classes="run-footer cancelled")
                )
                conversation.scroll_end(animate=False)
        except Exception as exc:  # noqa: BLE001 - UI boundary must remain usable
            if self.is_attached:
                await conversation.mount(
                    Static(
                        f"✗ FIN-AI stopped unexpectedly: {escape(str(exc))} · /debug for the full local trace",
                        classes="error",
                    )
                )
                self._refresh_chrome()
        finally:
            self._flush_response()
            if self.is_attached:
                self.post_message(RunFinished(task))

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
        self._refresh_chrome()
        self.query_one("#conversation", VerticalScroll).mount(
            Static("  ⎿ Approval rejected", classes="activity")
        )

    def action_cancel_run(self) -> None:
        if self._run_task and not self._run_task.done():
            self.state = PresentationState(
                phase=PresentationPhase.CANCELLING,
                run_id=self.state.run_id,
                query=self.state.query,
                response_text=self.state.response_text,
            )
            self._refresh_chrome()
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
        await conversation.mount(Static(render_welcome(), id="welcome"))
