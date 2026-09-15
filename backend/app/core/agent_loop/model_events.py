"""Pure helpers for normalizing provider stream payloads."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from app.services.hive_service import merge_tool_call_deltas


def merge_chunk_tool_calls(calls: dict[int, dict[str, Any]], chunk: Any) -> None:
    """Merge tool-call fragments from one provider chunk into ``calls``."""
    if not isinstance(chunk, dict):
        return
    choices = chunk.get("choices", [])
    delta = choices[0].get("delta", {}) if choices else {}
    if isinstance(delta, dict) and isinstance(delta.get("tool_calls"), list):
        merge_tool_call_deltas(calls, delta["tool_calls"])


def sanitize_tool_calls(calls: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace malformed streamed arguments with an empty object."""
    sanitized: list[dict[str, Any]] = []
    for call in calls:
        value = dict(call)
        function = dict(value.get("function") or {})
        if not str(function.get("name") or value.get("name") or "").strip():
            continue
        raw_arguments = function.get("arguments")
        if isinstance(raw_arguments, str):
            try:
                json.loads(raw_arguments)
            except json.JSONDecodeError:
                function["arguments"] = "{}"
                value["function"] = function
        sanitized.append(value)
    return sanitized


def result_payload(result: Any) -> dict[str, Any]:
    """Normalize a tool result for the model conversation."""
    if hasattr(result, "to_dict"):
        value = result.to_dict()
        return value if isinstance(value, dict) else {"data": value}
    if isinstance(result, dict):
        return result
    return {"data": result}
