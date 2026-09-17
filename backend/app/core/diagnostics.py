"""Opt-in, bounded diagnostics for investigating local pipeline failures."""

from __future__ import annotations

import json
import os
import re
from typing import Any

_SECRET_KEY = re.compile(
    r"(?i)(token|secret|password|api[-_]?key|authorization|cookie)"
)
_SECRET_VALUE = re.compile(r"(?i)(bearer\s+|api[-_]?key\s*[:=]\s*)[^\s,}]+")


def diagnostics_enabled() -> bool:
    """Return whether detailed diagnostics were explicitly requested."""
    return os.getenv("FINAI_DIAGNOSTICS", "").strip().casefold() in {
        "trace",
        "payloads",
    }


def diagnostic_payload(value: Any, *, max_chars: int = 65_536) -> str:
    """Serialize a bounded, redacted diagnostic value for local logs."""
    encoded = json.dumps(
        _redact(value), ensure_ascii=False, default=str, sort_keys=True
    )
    if len(encoded) <= max_chars:
        return encoded
    return encoded[: max_chars - 1] + "…"


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE.sub(r"\1[REDACTED]", value)
    return value
