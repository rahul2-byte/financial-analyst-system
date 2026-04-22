"""Dedupe keys and lightweight parsing for news payloads."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any


def sha256(value: str) -> str:
    """Return a stable SHA-256 hex digest for a UTF-8 string."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def dedupe_key_from_payload(payload: dict[str, Any]) -> str:
    """Best-effort dedupe key for vector-store chunk payloads.

    The vector store may contain different metadata shapes depending on pipeline
    version. This function implements the legacy priority order.
    """

    for key in ("dedupe_key", "article_hash", "canonical_url", "url", "link"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return sha256(text.strip()[:2048])
    return ""


def parse_iso_datetime(value: Any) -> datetime | None:
    """Parse an ISO datetime string to a timezone-aware datetime.

    Legacy behavior:
    - Accepts a `datetime` instance and returns it unchanged.
    - Accepts an ISO string; treats 'Z' as '+00:00'.
    - Returns None for invalid inputs.
    """

    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def article_dedupe_key(article: dict[str, Any]) -> str:
    """Best-effort dedupe key for normalized article dicts."""

    for key in (
        "dedupe_key",
        "article_hash",
        "canonical_url",
        "resolved_url",
        "original_url",
        "url",
        "link",
        "title",
    ):
        value = article.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


EPOCH_UTC = datetime.fromtimestamp(0, tz=UTC)
