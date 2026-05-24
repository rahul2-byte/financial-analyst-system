"""Dedupe keys and lightweight parsing for news payloads."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "ref",
    "source",
    "via",
    "mc_cid",
    "fbclid",
    "gclid",
}


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


def normalize_url_identity(value: Any) -> str:
    """Normalize a URL for deterministic same-article identity checks."""

    if not isinstance(value, str) or not value.strip():
        return ""

    parsed = urlparse(value.strip())
    kept_params = [
        (key, param_value)
        for key, param_value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in TRACKING_PARAMS
    ]
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            urlencode(sorted(kept_params)),
            "",
        )
    )


def news_url_identity(article: dict[str, Any]) -> str:
    """Return canonical URL first, then normalized raw URL/link, then hash fallback."""

    for key in ("canonical_url", "url", "link"):
        identity = normalize_url_identity(article.get(key))
        if identity:
            return identity
    for key in ("article_hash", "dedupe_key"):
        value = article.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def dedupe_articles_by_url(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first article for each canonical/raw URL identity."""

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for article in articles:
        identity = news_url_identity(article)
        if identity and identity in seen:
            continue
        if identity:
            seen.add(identity)
        deduped.append(article)
    return deduped


EPOCH_UTC = datetime.fromtimestamp(0, tz=UTC)
