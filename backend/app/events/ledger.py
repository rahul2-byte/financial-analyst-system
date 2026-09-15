"""Small, append-only execution ledger for local FIN-AI sessions."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_SECRET = re.compile(
    r"(?i)(authorization\s*[:=]\s*bearer\s+|api[_-]?key\s*[:=]\s*)[^\s,}]+"
)
_REDACTED = "[REDACTED]"


class TraceLedger:
    """Persist typed events as a single ordered JSONL stream.

    The ledger owns ordering; provider or UI sequence numbers are retained in
    the payload but never trusted as the canonical local order.
    """

    def __init__(self, session_dir: Path, inline_limit: int = 16_384) -> None:
        self.session_dir = session_dir
        self.path = session_dir / "events.v1.jsonl"
        self.artifacts_dir = session_dir / "artifacts"
        self.inline_limit = inline_limit
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._repair_torn_tail()
        self._sequence = self._last_sequence()

    def append(self, event: BaseModel, *, durable: bool = True) -> dict[str, Any]:
        payload = _redact(event.model_dump(mode="json"))
        meta = payload.pop("meta", {})
        event_type = str(payload.pop("type", event.__class__.__name__))
        record: dict[str, Any] = {
            "schema_version": 1,
            "event_id": str(meta.get("event_id", "")),
            "run_id": str(meta.get("run_id", "")),
            "conversation_id": str(meta.get("conversation_id", "")),
            "sequence": self._sequence + 1,
            "occurred_at": meta.get("occurred_at"),
            "event_type": event_type,
            "payload": payload,
            "artifact_refs": [],
        }
        encoded = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
        if len(encoded) > self.inline_limit:
            artifact = self._write_artifact(payload)
            record["payload"] = {"stored_as_artifact": True}
            record["artifact_refs"] = [{"sha256": artifact[0], "path": artifact[1]}]
        self._sequence += 1
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            # A local trace must survive a cancelled process at a semantic
            # boundary; callers can choose to batch non-critical events later.
            if durable:
                os.fsync(handle.fileno())
        return record

    def append_raw(
        self,
        *,
        event_type: str,
        run_id: str,
        conversation_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Append a recovery fact when no live typed event object exists."""
        return self._append_record(
            event_type=event_type,
            meta={
                "event_id": "recovery",
                "run_id": run_id,
                "conversation_id": conversation_id,
                "occurred_at": datetime.now(UTC).isoformat(),
            },
            payload=payload,
        )

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        raw = self.path.read_text(encoding="utf-8")
        lines = raw.splitlines()
        records: list[dict[str, Any]] = []
        for index, line in enumerate(lines):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    if index == len(lines) - 1 and not raw.endswith("\n"):
                        break
                    raise
        return records

    def _last_sequence(self) -> int:
        records = self.read()
        if not records:
            return 0
        sequence = records[-1].get("sequence", 0)
        if not isinstance(sequence, int):
            raise TypeError("trace sequence must be an integer")
        return sequence

    def _repair_torn_tail(self) -> None:
        if not self.path.exists():
            return
        raw = self.path.read_bytes()
        if not raw or raw.endswith(b"\n"):
            return
        lines = raw.splitlines(keepends=True)
        try:
            json.loads(lines[-1].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.path.write_bytes(b"".join(lines[:-1]))

    def _write_artifact(self, payload: dict[str, Any]) -> tuple[str, str]:
        content = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        relative = Path("artifacts") / f"{digest}.json"
        target = self.session_dir / relative
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(content)
        return digest, str(relative)

    def _append_record(
        self, *, event_type: str, meta: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "schema_version": 1,
            "event_id": str(meta.get("event_id", "")),
            "run_id": str(meta.get("run_id", "")),
            "conversation_id": str(meta.get("conversation_id", "")),
            "sequence": self._sequence + 1,
            "occurred_at": meta.get("occurred_at"),
            "event_type": event_type,
            "payload": _redact(payload),
            "artifact_refs": [],
        }
        self._sequence += 1
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            import os

            os.fsync(handle.fileno())
        return record


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return _SECRET.sub(r"\1" + _REDACTED, value)
    if isinstance(value, dict):
        return {str(key): _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
