"""Project-local persistence for conversations, runs, and context artifacts."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.events.ledger import TraceLedger
from app.models.request_models import Message

logger = logging.getLogger(__name__)


class SessionStore:
    def __init__(self, root: Path, session_id: str) -> None:
        self.root = root
        self.session_id = session_id
        self.session_dir = root / "sessions" / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.trace = TraceLedger(self.session_dir)

    @property
    def transcript_path(self) -> Path:
        return self.session_dir / "transcript.jsonl"

    @property
    def events_path(self) -> Path:
        return self.session_dir / "events.jsonl"

    def load_history(self) -> list[Message]:
        if self.transcript_path.exists():
            messages: list[Message] = []
            for line in self.transcript_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("kind") == "message":
                    messages.append(Message.model_validate(record["message"]))
            return messages

        return []

    def append_message(self, message: Message) -> None:
        self._append_jsonl(
            self.transcript_path,
            {
                "kind": "message",
                "message": message.model_dump(mode="json"),
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

    def append_events(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            self._append_jsonl(self.events_path, event)

    def append_trace_event(self, event: Any) -> dict[str, Any]:
        """Append one typed execution event before the next operation starts."""
        record = self.trace.append(event, durable=event.type != "response.delta")
        logger.debug(
            "trace persisted event_type=%s sequence=%s run_id=%s",
            record["event_type"],
            record["sequence"],
            record["run_id"],
        )
        return record

    def write_run(
        self,
        *,
        query: str,
        events: list[dict[str, Any]],
        run_id: str,
        status: str,
    ) -> Path:
        run_dir = self.session_dir / "runs"
        run_dir.mkdir(parents=True, exist_ok=True)
        target = run_dir / f"{run_id}.json"
        self._atomic_json(
            target,
            {
                "run_id": run_id,
                "session_id": self.session_id,
                "query": query,
                "status": status,
                "created_at": datetime.now(UTC).isoformat(),
                "events": events,
            },
        )
        self.append_events(events)
        return target

    def begin_run(self, *, query: str, run_id: str) -> Path:
        """Persist the accepted run before downstream work can be interrupted."""
        return self.write_run(query=query, events=[], run_id=run_id, status="running")

    def write_context(self, context: dict[str, Any]) -> None:
        self._atomic_json(self.session_dir / "context.json", context)

    def read_context(self) -> dict[str, Any]:
        return self._read_json(self.session_dir / "context.json")

    def write_pending(self, pending: dict[str, Any]) -> None:
        self._atomic_json(self.session_dir / "pending.json", pending)

    def write_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        """Persist the exact model/tool boundary needed for a safe resume."""
        self._atomic_json(self.session_dir / "checkpoint.json", checkpoint)

    def read_checkpoint(self) -> dict[str, Any] | None:
        path = self.session_dir / "checkpoint.json"
        return self._read_json(path) if path.exists() else None

    def clear_checkpoint(self) -> None:
        path = self.session_dir / "checkpoint.json"
        if path.exists():
            path.unlink()

    def read_pending(self) -> dict[str, Any] | None:
        path = self.session_dir / "pending.json"
        return self._read_json(path) if path.exists() else None

    def mark_incomplete_runs_interrupted(self) -> int:
        """Mark abandoned local runs so resume never presents them as active."""
        runs_dir = self.session_dir / "runs"
        if not runs_dir.exists():
            return 0
        changed = 0
        for path in runs_dir.glob("*.json"):
            try:
                payload = self._read_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("status") != "running":
                continue
            payload["status"] = "interrupted"
            payload["interrupted_at"] = datetime.now(UTC).isoformat()
            self._atomic_json(path, payload)
            run_id = str(payload.get("run_id", path.stem))
            trace_records = self.trace.read()
            has_terminal = any(
                record.get("run_id") == run_id
                and record.get("event_type")
                in {
                    "run.completed",
                    "run.failed",
                    "run.cancelled",
                    "run.interrupted",
                }
                for record in trace_records
            )
            if not has_terminal:
                self.trace.append_raw(
                    event_type="run.interrupted",
                    run_id=run_id,
                    conversation_id=self.session_id,
                    payload={"reason": "process ended before run completion"},
                )
            changed += 1
        return changed

    def clear_pending(self) -> None:
        path = self.session_dir / "pending.json"
        if path.exists():
            path.unlink()
        self.clear_checkpoint()

    @staticmethod
    def list_sessions(root: Path) -> list[dict[str, str]]:
        sessions_dir = root / "sessions"
        if not sessions_dir.exists():
            return []
        sessions: list[dict[str, str]] = []
        for directory in sessions_dir.iterdir():
            if not directory.is_dir():
                continue
            transcript = directory / "transcript.jsonl"
            title = "New research session"
            message_count = 0
            last_status = "unknown"
            last_activity = ""
            if transcript.exists():
                for line in transcript.read_text(encoding="utf-8").splitlines():
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    message = record.get("message", {})
                    if (
                        record.get("kind") == "message"
                        and message.get("role") == "user"
                    ):
                        message_count += 1
                        title = str(message.get("content", title)).splitlines()[0][:72]
                    elif record.get("kind") == "message":
                        message_count += 1
                    last_activity = str(record.get("created_at", last_activity))
            run_files = (
                sorted((directory / "runs").glob("*.json"))
                if (directory / "runs").exists()
                else []
            )
            if run_files:
                try:
                    last_run = json.loads(run_files[-1].read_text(encoding="utf-8"))
                    last_status = str(last_run.get("status", last_status))
                    last_activity = str(last_run.get("created_at", last_activity))
                except (OSError, json.JSONDecodeError):
                    pass
            sessions.append(
                {
                    "id": directory.name,
                    "title": title,
                    "message_count": str(message_count),
                    "run_count": str(len(run_files)),
                    "last_status": last_status,
                    "last_activity": last_activity,
                }
            )
        return sorted(sessions, key=lambda item: item["id"], reverse=True)

    def _append_jsonl(self, path: Path, value: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, default=str) + "\n")

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _atomic_json(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
