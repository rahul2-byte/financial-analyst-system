"""Modal screens for FIN-AI terminal decisions and session navigation."""

from __future__ import annotations

from typing import ClassVar

from rich.markup import escape
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static


class ApprovalScreen(ModalScreen[bool | None]):
    """Keyboard-first approval gate for a runtime-generated question."""

    BINDINGS: ClassVar[list[tuple[str, str] | tuple[str, str, str]]] = [  # type: ignore[assignment]
        ("y", "approve", "Approve"),
        ("n", "reject", "Reject"),
        ("d", "details", "Details"),
        ("up", "cursor_up", "Previous"),
        ("down", "cursor_down", "Next"),
        ("enter", "select", "Confirm"),
        ("escape", "reject", "Reject"),
    ]

    def __init__(self, prompt: str, details: str | None = None) -> None:
        super().__init__()
        self.prompt = prompt
        self.details = details
        self._selected = 0
        self._show_details = False

    def _body(self) -> str:
        choices = ("Approve", "Reject", "Details")
        lines = [
            f"  {'›' if index == self._selected else ' '} {choice}"
            for index, choice in enumerate(choices)
        ]
        details = (
            f"\n\n{escape(self.details)}" if self._show_details and self.details else ""
        )
        return (
            "Approval required\n\n"
            + escape(self.prompt)
            + details
            + "\n\n"
            + "\n".join(lines)
            + "\n\n↑↓ select · Enter confirm · Esc reject"
        )

    def compose(self) -> ComposeResult:
        yield Static(self._body(), id="approval-modal")

    def _refresh(self) -> None:
        self.query_one("#approval-modal", Static).update(self._body())

    def action_approve(self) -> None:
        self.dismiss(True)

    def action_reject(self) -> None:
        self.dismiss(False)

    def action_details(self) -> None:
        self._show_details = not self._show_details
        self._refresh()

    def action_cursor_down(self) -> None:
        self._selected = (self._selected + 1) % 3
        self._refresh()

    def action_cursor_up(self) -> None:
        self._selected = (self._selected - 1) % 3
        self._refresh()

    def action_select(self) -> None:
        (self.action_approve, self.action_reject, self.action_details)[self._selected]()


class SessionScreen(ModalScreen[str | None]):
    """Compact keyboard-navigable local session picker."""

    BINDINGS: ClassVar[list[tuple[str, str] | tuple[str, str, str]]] = [  # type: ignore[assignment]
        ("up", "previous", "Previous"),
        ("down", "next", "Next"),
        ("enter", "select", "Resume"),
        ("escape", "cancel", "Close"),
    ]

    def __init__(self, sessions: list[dict[str, str]]) -> None:
        super().__init__()
        self.sessions = sessions
        self.selected = 0

    def compose(self) -> ComposeResult:
        yield Static(self._body(), id="session-modal")

    def _body(self) -> str:
        lines = ["Select a session", "Search and resume previous research.", ""]
        for index, session in enumerate(self.sessions):
            marker = "›" if index == self.selected else " "
            lines.append(f"{marker} {session['title'][:42]}")
            lines.append(
                f"    {session['message_count']} messages · {session['last_status']}"
                f" · {session['id'][:8]}"
            )
        lines.append("\n↑↓ select · Enter resume · Esc close")
        return "\n".join(lines) if self.sessions else "No saved sessions\n\nEsc close"

    def _refresh(self) -> None:
        self.query_one("#session-modal", Static).update(self._body())

    def action_previous(self) -> None:
        if self.sessions:
            self.selected = (self.selected - 1) % len(self.sessions)
            self._refresh()

    def action_next(self) -> None:
        if self.sessions:
            self.selected = (self.selected + 1) % len(self.sessions)
            self._refresh()

    def action_select(self) -> None:
        if self.sessions:
            self.dismiss(self.sessions[self.selected]["id"])

    def action_cancel(self) -> None:
        self.dismiss(None)
