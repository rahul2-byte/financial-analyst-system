"""Pure formatting helpers for slash-command output."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.models.request_models import Message

from .context_budget import ContextBudget
from .state import PresentationState


def status_text(state: PresentationState) -> str:
    return f"\nFIN-AI · {state.phase.value} · sequence {state.latest_sequence}"


def history_text(history: Sequence[Message]) -> str:
    return "\n" + "\n".join(f"{message.role}: {message.content}" for message in history)


def queries_text(queries: Sequence[str]) -> str:
    if not queries:
        return "No prior queries in this session."
    lines = [f"Session history · {len(queries)} queries"]
    lines.extend(
        f"  {index}. {query.splitlines()[0][:100] if query else ''}"
        for index, query in enumerate(queries, 1)
    )
    return "\n".join(lines)


def mode_error_text(value: str, modes: Sequence[str]) -> str:
    return f"Invalid mode '{value}'. Valid modes: {', '.join(modes)}"


def context_text(
    message_count: int, estimated: int, budget: ContextBudget, stored: dict[str, Any]
) -> str:
    percent = 100 * estimated / budget.max_tokens if budget.max_tokens else 0
    lines = [
        "Context",
        f"  messages     {message_count}",
        f"  tokens       ~{estimated} / {budget.max_tokens} ({percent:.1f}%)",
        f"  compact at   {budget.compaction_limit}",
    ]
    if stored.get("compacted_messages"):
        lines.append(f"  last compact {stored['compacted_messages']} messages")
    return "\n".join(lines)


def trace_text(
    records: Sequence[dict[str, Any]], ledger_path: Path, *, as_json: bool = False
) -> str:
    if as_json:
        return json.dumps(list(records), indent=2, ensure_ascii=False)
    lines = [
        "\nTrace",
        f"  ledger       {ledger_path}",
        f"  events       {len(records)}",
    ]
    lines.extend(
        f"  #{record['sequence']} {record['event_type']}" for record in records[-12:]
    )
    return "\n".join(lines)
