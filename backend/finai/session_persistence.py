"""Persistence boundary for a FIN-AI conversation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.models.request_models import Message

from .session_store import SessionStore


class SessionPersistence:
    """Keep filesystem side effects behind the existing ``SessionStore``."""

    def __init__(self, store: SessionStore) -> None:
        self.store = store

    @property
    def session_dir(self) -> Path:
        return self.store.session_dir

    def load_history(self) -> list[Message]:
        return self.store.load_history()

    def append_message(self, message: Message) -> None:
        self.store.append_message(message)

    def write_checkpoint(self, payload: dict[str, Any]) -> None:
        self.store.write_checkpoint(payload)

    def write_pending(self, payload: dict[str, Any]) -> None:
        self.store.write_pending(payload)

    def clear_pending(self) -> None:
        self.store.clear_pending()

    def write_run(
        self,
        *,
        query: str,
        run_id: str,
        status: str,
        events: list[dict[str, Any]],
    ) -> Path:
        return self.store.write_run(
            query=query,
            run_id=run_id,
            status=status,
            events=events,
        )
