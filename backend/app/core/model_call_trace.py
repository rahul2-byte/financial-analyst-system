"""Opt-in, local full-text traces for model provider calls."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from app.config import settings

_TRACE_DIR_MARKER = ".finai-model-call-traces"


@dataclass(frozen=True)
class ModelCallTrace:
    path: Path
    call_id: str
    provider: str
    model: str
    run_id: str | None
    conversation_id: str | None

    @classmethod
    def create(
        cls,
        *,
        provider: str,
        model: str,
        run_id: str | None = None,
        conversation_id: str | None = None,
        call_id: str | None = None,
    ) -> ModelCallTrace | None:
        """Create a trace file only after the operator explicitly opts in."""
        trace_mode = os.getenv("FINAI_MODEL_TRACE", settings.FINAI_MODEL_TRACE)
        if trace_mode.strip().casefold() != "full":
            return None
        configured_root = os.getenv(
            "FINAI_MODEL_TRACE_DIR", settings.FINAI_MODEL_TRACE_DIR
        ).strip()
        root = Path(configured_root or ".finai/model-traces").expanduser()
        _prune_expired(root)
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        day_dir = root / datetime.now(UTC).date().isoformat()
        created_day_dir = not day_dir.exists()
        day_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if created_day_dir:
            marker = day_dir / _TRACE_DIR_MARKER
            descriptor = os.open(
                marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
            os.close(descriptor)
        trace_id = call_id or str(uuid4())
        group_id = run_id or conversation_id or trace_id
        safe_group_id = re.sub(r"[^A-Za-z0-9_-]", "_", group_id)[:128]
        path = day_dir / f"{safe_group_id}.jsonl"
        return cls(path, trace_id, provider, model, run_id, conversation_id)

    def write(self, event: str, payload: dict[str, Any]) -> None:
        """Append and fsync one JSONL record without recording HTTP headers."""
        record = {
            "schema_version": 1,
            "event": event,
            "occurred_at": datetime.now(UTC).isoformat(),
            "call_id": self.call_id,
            "run_id": self.run_id,
            "conversation_id": self.conversation_id,
            "provider": self.provider,
            "model": self.model,
            "payload": payload,
        }
        encoded = (json.dumps(record, ensure_ascii=False, default=str) + "\n").encode()
        descriptor = os.open(self.path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            view = memoryview(encoded)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def call_started(
    trace: ModelCallTrace | None,
    *,
    messages: list[Any],
    tools: list[dict[str, Any]] | None,
    parameters: dict[str, Any],
) -> None:
    if trace is None:
        return
    trace.write(
        "call.started",
        {
            "request_messages": [
                message.model_dump(mode="json")
                if hasattr(message, "model_dump")
                else message
                for message in messages
            ],
            "tools": tools,
            "parameters": parameters,
        },
    )


async def capture_stream(
    trace: ModelCallTrace,
    events: Any,
) -> Any:
    """Copy text and tool-call fragments into one complete terminal trace record."""
    text: list[str] = []
    tool_calls: dict[int, dict[str, Any]] = {}
    chunk_timings: list[dict[str, float | int]] = []
    provider_events: list[dict[str, Any]] = []
    started = time.perf_counter()
    try:
        async for event in events:
            name = event.get("event")
            if name == "token":
                delta = event.get("data", "")
                text.append(str(delta))
                chunk_timings.append(
                    {
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                        "characters": len(str(delta)),
                    }
                )
                chunk = event.get("chunk")
                if chunk is not None:
                    _merge_tool_calls(tool_calls, chunk)
            elif name == "chunk":
                chunk = event.get("data")
                _merge_tool_calls(tool_calls, chunk)
                chunk_timings.append(
                    {
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                        "characters": len(json.dumps(chunk, default=str)),
                    }
                )
            elif name in {
                "provider_attempt_started",
                "provider_retrying",
                "provider_stream_started",
                "provider_completed",
                "provider_failed",
            }:
                provider_events.append({"event": name, "data": event.get("data", {})})
            yield event
        trace.write(
            "call.completed",
            {
                "text": "".join(text),
                "tool_calls": [tool_calls[index] for index in sorted(tool_calls)],
                "chunk_timings": chunk_timings,
                "provider_events": provider_events,
            },
        )
    except BaseException as exc:
        trace.write(
            "call.failed",
            {
                "text": "".join(text),
                "tool_calls": [tool_calls[index] for index in sorted(tool_calls)],
                "chunk_timings": chunk_timings,
                "provider_events": provider_events,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        raise


def _merge_tool_calls(calls: dict[int, dict[str, Any]], chunk: Any) -> None:
    if not isinstance(chunk, dict):
        return
    choices = chunk.get("choices", [])
    delta = choices[0].get("delta", {}) if choices else {}
    deltas = delta.get("tool_calls", []) if isinstance(delta, dict) else []
    for item in deltas:
        if not isinstance(item, dict) or not isinstance(item.get("index"), int):
            continue
        target = calls.setdefault(item["index"], {})
        for key in ("id", "type"):
            if item.get(key):
                target[key] = item[key]
        function = item.get("function")
        if isinstance(function, dict):
            current = target.setdefault("function", {})
            if function.get("name"):
                current["name"] = function["name"]
            if function.get("arguments"):
                current["arguments"] = current.get("arguments", "") + str(
                    function["arguments"]
                )


def _prune_expired(root: Path) -> None:
    if not root.is_dir():
        return
    cutoff = datetime.now(UTC).timestamp() - timedelta(days=7).total_seconds()
    for child in root.iterdir():
        if child.is_symlink() or not child.is_dir():
            continue
        try:
            date.fromisoformat(child.name)
            expired = child.stat().st_mtime < cutoff
        except OSError:
            continue
        except ValueError:
            continue
        marker = child / _TRACE_DIR_MARKER
        if not expired or marker.is_symlink() or not marker.is_file():
            continue
        contents = list(child.iterdir())
        if any(
            entry != marker
            and (
                entry.is_symlink()
                or not entry.is_file()
                or entry.suffix != ".jsonl"
                or not _is_trace_file(entry)
            )
            for entry in contents
        ):
            continue
        for entry in contents:
            if entry != marker:
                entry.unlink()
        marker.unlink()
        try:
            child.rmdir()
        except OSError:
            # Preserve any file added concurrently rather than recursively deleting it.
            marker.touch(mode=0o600, exist_ok=True)


def _is_trace_file(path: Path) -> bool:
    try:
        first_line = path.open(encoding="utf-8").readline()
        record = json.loads(first_line)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(record, dict)
        and record.get("schema_version") == 1
        and record.get("event") == "call.started"
        and isinstance(record.get("call_id"), str)
        and isinstance(record.get("provider"), str)
        and isinstance(record.get("model"), str)
        and isinstance(record.get("payload"), dict)
    )


def read_trace(path: Path) -> list[dict[str, Any]]:
    """Read complete JSONL records and ignore a torn final append after a crash."""
    if not path.exists():
        return []
    raw = path.read_bytes()
    lines = raw.splitlines()
    records: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            if index == len(lines) - 1 and not raw.endswith(b"\n"):
                break
            raise
        if not isinstance(value, dict):
            raise TypeError("model-call trace record must be a JSON object")
        records.append(value)
    return records


def safe_endpoint(value: str) -> str:
    """Keep endpoint identity while omitting credentials and URL parameters."""
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.hostname:
        return value
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
