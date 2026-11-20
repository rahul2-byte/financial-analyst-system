"""Reusable Textual widgets for the FIN-AI terminal."""

from __future__ import annotations

from typing import Any

from rich.console import RenderableType
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message as TextualMessage
from textual.widgets import Button, Static, TextArea


class UserMessage(Static):
    """A stable, visually distinct user turn."""


class AssistantMessage(Horizontal):
    """One assistant turn: a ledger bullet and a body updated as deltas arrive."""

    def __init__(self, content: RenderableType = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.body = Static(content, classes="assistant-body")

    def compose(self) -> ComposeResult:
        yield Static("●", classes="assistant-bullet")
        yield self.body

    def update(self, content: RenderableType) -> None:
        self.body.update(content)


class RunActivity(Static):
    """One compact activity trail per run, updated in place."""


class CommandMessage(Static):
    """A command invocation, separate from user and assistant turns."""


class AppHeader(Static):
    """One-line brand and session chrome."""


class NavigationRail(Vertical):
    """Small rail containing actions already available through slash commands."""

    def compose(self):
        yield Static("NAVIGATION", classes="rail-title")
        yield Button("▌ New Research", id="nav-new", classes="nav-item -active")
        yield Button("Sessions", id="nav-sessions", classes="nav-item")
        yield Button("Trace", id="nav-trace", classes="nav-item")
        yield Button("Reports", id="nav-reports", classes="nav-item")
        yield Static("", id="recent-sessions", classes="recent-sessions")

    def show_sessions(
        self, sessions: list[dict[str, str]], active: str | None = None
    ) -> None:
        text = Text("RECENT SESSIONS\n", style="bold")
        if not sessions:
            text.append("\nNo saved sessions yet", style="dim")
        for session in sessions[:5]:
            marker = "●" if session["id"] == active else "○"
            text.append(f"\n{marker} {session['title'][:26]}\n")
            text.append(f"  {session['id'][:8]}\n", style="dim")
        self.query_one("#recent-sessions", Static).update(text)


class ContextRail(Static):
    """Live, evidence-bound research context."""


class Composer(TextArea):
    """Multiline editor with Enter-to-submit and Shift+Enter for a newline."""

    class Submitted(TextualMessage):
        def __init__(self, composer: Composer, value: str) -> None:
            super().__init__()
            self.composer = composer
            self.value = value

    def on_key(self, event) -> None:
        if event.key == "ctrl+z":
            event.stop()
            action = getattr(self.app, "action_quit_app", None)
            if action is not None:
                action()
        elif event.key == "ctrl+k":
            # TextArea binds ctrl+k to delete-to-line-end; the app owns it.
            event.stop()
            self.app.call_later(self.app.run_action, "sessions")
        elif event.key == "enter":
            event.stop()
            self.post_message(self.Submitted(self, self.text))
