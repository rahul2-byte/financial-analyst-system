"""Per-model-call latency and token records (no prompt or response text)."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

METRICS_FILE = "model-calls.jsonl"


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def build_call_record(
    *,
    purpose: str,
    model: str,
    status: str,
    ttft_ms: float | None,
    total_ms: float,
    usage: dict[str, Any] | None,
    retries: int,
    reasoning: dict[str, Any] | None,
    reasoning_chars: int = 0,
    run_id: str | None = None,
    call_id: str | None = None,
) -> dict[str, Any]:
    usage = usage if isinstance(usage, dict) else {}
    completion_details = usage.get("completion_tokens_details")
    prompt_details = usage.get("prompt_tokens_details")
    reasoning_tokens = _int(usage.get("reasoning_tokens"))
    if reasoning_tokens is None and isinstance(completion_details, dict):
        reasoning_tokens = _int(completion_details.get("reasoning_tokens"))
    cached_tokens = (
        _int(prompt_details.get("cached_tokens"))
        if isinstance(prompt_details, dict)
        else None
    )
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "call_id": call_id,
        "purpose": purpose,
        "model": model,
        "status": status,
        "ttft_ms": ttft_ms,
        "total_ms": total_ms,
        "prompt_tokens": _int(usage.get("prompt_tokens")),
        "completion_tokens": _int(usage.get("completion_tokens")),
        "reasoning_tokens": reasoning_tokens,
        "cached_tokens": cached_tokens,
        "reasoning_chars": reasoning_chars,
        "retries": retries,
        "repair": purpose == "repair",
        "reasoning_param": reasoning,
    }


def write_call_record(record: dict[str, Any]) -> None:
    """Append one JSONL record; never raises into the model call."""
    if not settings.FINAI_CALL_METRICS:
        return
    try:
        root = Path(settings.FINAI_CALL_METRICS_DIR).expanduser()
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        encoded = (json.dumps(record, ensure_ascii=False, default=str) + "\n").encode()
        fd = os.open(root / METRICS_FILE, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        try:
            os.write(fd, encoded)
        finally:
            os.close(fd)
    except OSError:
        logger.debug("call metrics write failed", exc_info=True)
