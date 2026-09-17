"""Reusable Textual widgets for the FIN-AI terminal."""

from __future__ import annotations

from textual.containers import Vertical
from textual.message import Message as TextualMessage
from textual.widgets import Button, Static, TextArea


class UserMessage(Static):
    """A stable, visually distinct user turn."""


class AssistantMessage(Static):
    """A single assistant turn updated as response deltas arrive."""


class RunActivity(Static):
    """One live activity view for one run; never duplicated per event."""


class CommandMessage(Static):
    """A command invocation, separate from user and assistant turns."""


class AppHeader(Static):
    """Persistent identity and run-status chrome."""


class NavigationRail(Vertical):
    """Small rail containing actions already available through slash commands."""

    def compose(self):
        yield Static("NAVIGATION", classes="rail-title")
        yield Button("▌ New Research", id="nav-new", classes="nav-item -active")
        yield Button("Sessions", id="nav-sessions", classes="nav-item")
        yield Button("Trace", id="nav-trace", classes="nav-item")
        yield Button("Reports", id="nav-reports", classes="nav-item")
        yield Button("Watchlist", id="nav-watchlist", classes="nav-item")
        yield Button("Settings", id="nav-settings", classes="nav-item")
        yield Static(
            "\nRECENT SESSIONS\n\n● HDFC Bank Analysis\n  Just now\n\n● Reliance Industries\n  2 hours ago\n\n● TCS Q4 Results\n  5 hours ago",
            classes="recent-sessions",
        )


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
        elif event.key == "enter":
            event.stop()
            self.post_message(self.Submitted(self, self.text))
