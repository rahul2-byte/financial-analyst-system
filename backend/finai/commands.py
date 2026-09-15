"""Slash-command parsing for the interactive terminal."""

from __future__ import annotations

import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    name: str
    description: str


class CommandRegistry:
    def __init__(self, commands: tuple[Command, ...]) -> None:
        self._commands = {command.name: command for command in commands}

    @classmethod
    def default(cls) -> CommandRegistry:
        return cls(
            tuple(
                Command(name, description)
                for name, description in (
                    ("help", "Show commands"),
                    ("clear", "Clear the conversation display"),
                    ("new", "Start a new conversation"),
                    ("sources", "Show sources from the last run"),
                    ("status", "Show current run status"),
                    ("debug", "Show last event and error details"),
                    ("trace", "Show the current execution trace"),
                    ("logs", "Show local run artifact location"),
                    ("mode", "Choose guided, review, or autonomous mode"),
                    ("context", "Show context budget and compaction state"),
                    ("compact", "Compact the current conversation now"),
                    ("sessions", "List project-local sessions"),
                    ("resume", "Resume a saved session by id"),
                    ("history", "Show the current session transcript"),
                    ("retry", "Retry the last request"),
                    ("exit", "Exit FIN-AI"),
                )
            )
        )

    def get(self, name: str) -> Command | None:
        return self._commands.get(name.removeprefix("/"))

    @property
    def commands(self) -> tuple[Command, ...]:
        return tuple(self._commands.values())

    def suggestions(self, prefix: str) -> list[str]:
        return [name for name in self._commands if name.startswith(prefix.lower())]

    def suggestion_items(self, prefix: str) -> list[Command]:
        return [
            command
            for command in self._commands.values()
            if command.name.startswith(prefix.lower())
        ]

    def help_text(self) -> str:
        """Return the user-facing slash-command reference."""
        return "\n".join(
            f"/{command.name}  {command.description}" for command in self.commands
        )



def parse_command(text: str) -> tuple[str | None, list[str]]:
    text = text.strip()
    if not text.startswith("/"):
        return None, [text] if text else []
    try:
        parts = shlex.split(text[1:])
    except ValueError:
        return None, []
    return (parts[0], parts[1:]) if parts else (None, [])
