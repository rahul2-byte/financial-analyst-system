"""Pure formatting helpers for slash-command output."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.models.request_models import Message

from .state import PresentationState


def status_text(state: PresentationState) -> str:
    return f"\nFIN-AI · {state.phase.value} · sequence {state.latest_sequence}"


def history_text(history: Sequence[Message]) -> str:
    return "\n" + "\n".join(f"{message.role}: {message.content}" for message in history)


def trace_text(records: Sequence[dict[str, Any]], ledger_path: Path, *, as_json: bool = False) -> str:
    if as_json:
        return json.dumps(list(records), indent=2, ensure_ascii=False)
    lines = ["\nTrace", f"  ledger       {ledger_path}", f"  events       {len(records)}"]
    lines.extend(
        f"  #{record['sequence']} {record['event_type']}" for record in records[-12:]
    )
    return "\n".join(lines)
