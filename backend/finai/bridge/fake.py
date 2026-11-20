"""Event-replaying stand-in for ``FinAIRepl`` used by the bridge and tests.

``FakeRepl`` exposes the exact surface the bridge server uses from
``FinAIRepl`` (``typed_stream``, ``mode``, session fields, ``store``,
``new_session``/``resume_session``/``compact_context``/``aclose``), so the
server can talk to either interchangeably.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.events.models import ResearchEvent
from pydantic import TypeAdapter

_ADAPTER: TypeAdapter[ResearchEvent] = TypeAdapter(ResearchEvent)


class _FakeTrace:
    def __init__(self, root: Path, session_id: str) -> None:
        self.path = root / "sessions" / session_id / "events.v1.jsonl"

    def read(self) -> list[dict[str, Any]]:
        return []


class _FakeStore:
    """Minimal ``SessionStore`` stand-in for the bridge server."""

    def __init__(self, root: Path, session_id: str) -> None:
        self.root = root
        self.session_id = session_id
        self.trace = _FakeTrace(root, session_id)

    def list_sessions(self, root: Path) -> list[dict[str, str]]:
        return [
            {
                "id": self.session_id,
                "title": "New research session",
                "message_count": "0",
                "run_count": "0",
                "last_status": "unknown",
                "last_activity": "",
            }
        ]

    def read_context(self) -> dict[str, Any]:
        return {}


class FakeRepl:
    """Replays a fixed event list; ``typed_stream`` sleeps ``delay_ms`` per event."""

    def __init__(
        self,
        events: Sequence[ResearchEvent] | None = None,
        *,
        root: Path | None = None,
        session_id: str = "fake-session",
        delay_ms: int = 0,
        material: dict[str, Any] | None = None,
    ) -> None:
        self._material = material
        self.root = Path(root) if root is not None else Path(".finai")
        self.session_id = session_id
        self.mode = "guided"
        self.store = _FakeStore(self.root, self.session_id)
        self.history: list[Any] = []
        self._events: list[ResearchEvent] = list(events or [])
        self._delay_s = delay_ms / 1000.0

    @staticmethod
    def load_events(path: Path | str) -> list[ResearchEvent]:
        """Load the ``hdfc_run_events.json`` fixture, filling missing meta fields."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        events: list[ResearchEvent] = []
        for item in raw:
            meta = dict(item.get("meta") or {})
            meta.setdefault("event_id", uuid4())
            meta.setdefault("occurred_at", datetime.now(UTC))
            events.append(_ADAPTER.validate_python({**item, "meta": meta}))
        return events

    async def typed_stream(self, query: str) -> AsyncIterator[ResearchEvent]:
        del query  # the fixture stream ignores the query
        for event in self._events:
            if self._delay_s:
                await asyncio.sleep(self._delay_s)
            yield event

    def last_report_material(self) -> dict[str, Any] | None:
        return self._material

    def new_session(self) -> None:
        self.session_id = uuid4().hex

    def resume_session(self, session_id: str) -> None:
        self.session_id = session_id

    def compact_context(self) -> dict[str, int | str]:
        return {"compacted_messages": 0, "estimated_tokens": 0}

    async def aclose(self) -> None:
        return None


__all__ = ["FakeRepl"]
