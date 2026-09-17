"""Command dispatch for the FIN-AI terminal."""

from __future__ import annotations

from typing import Any

from textual.containers import VerticalScroll
from textual.widgets import Static

from .app_commands import status_text, trace_text
from .render import render_command, render_debug, render_sources
from .state import PresentationState
from .widgets import CommandMessage


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

    async def _command(self, name: str, args: list[str]) -> None:
        conversation = self.query_one("#conversation", VerticalScroll)
        await conversation.mount(
            CommandMessage(render_command(name, args), classes="command-message")
        )
        if name == "help":
            await conversation.mount(Static("\n" + self.registry.help_text()))
        elif name in {"clear", "new"}:
            await conversation.remove_children()
            self.state = PresentationState()
            self._response_widget = None
            self._activity_widget = None
            if name == "new" and self.new_session_callback:
                self.new_session_callback()
        elif name == "status":
            await conversation.mount(Static(status_text(self.state)))
        elif name == "debug":
            await conversation.mount(Static(render_debug(self.state, self._event_log)))
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
        elif name == "logs":
            await conversation.mount(
                Static("\nRun artifacts: .finai/sessions/<session>/runs/")
            )
        elif name == "mode":
            await conversation.mount(
                Static(f"\nMode · {args[0]}" if args else f"\nMode · {self.mode}")
            )
        elif name == "exit":
            self.exit()
