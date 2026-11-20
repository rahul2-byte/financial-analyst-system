"""Plain and JSON event renderers for pipes, CI, and debugging."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

from app.events.models import ResearchEvent
from app.security.policy import redact_secrets

from .safety import sanitize_terminal_text

_PROVIDER_LABELS = {
    "yfinance": "Yahoo Finance",
    "yahoo": "Yahoo Finance",
    "upstox": "Upstox",
    "tinyfish": "TinyFish news",
}
_DATASET_LABELS = {
    "history": "price history",
    "financials": "financials",
    "key-statistics": "key statistics",
    "news": "news",
}
_REASON_LABELS = {
    "quota": "quota reached",
    "auth": "authentication failed",
    "rate_limit": "rate limited",
    "server_error": "provider server error",
    "timeout": "timed out",
    "error": "error",
}
REVIEW_UNAVAILABLE_NOTE = (
    "Note: independent answer review was unavailable; "
    "numbers were checked against tool evidence."
)
_PYDANTIC_VALUE_ERROR = re.compile(r"Value error, (.*?)(?: \[type=|\n|$)")


def dedupe_sources(sources: list[dict[str, str]]) -> list[dict[str, str]]:
    """Drop repeated sources, keyed by url and label."""
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for source in sources:
        key = (source.get("url", ""), source_label(source))
        if key in seen:
            continue
        seen.add(key)
        unique.append(source)
    return unique


def source_label(source: dict[str, str]) -> str:
    """Readable label: explicit title, else provider · dataset · instrument."""
    title = source.get("title")
    if title:
        return title
    raw = (source.get("name") or source.get("source") or "").strip()
    provider = _PROVIDER_LABELS.get(raw.lower(), raw)
    parts = [provider] if provider else []
    segments = [
        part for part in urlparse(source.get("url", "")).path.split("/") if part
    ]
    if len(segments) >= 2 and segments[0] == "quote":
        dataset = segments[2] if len(segments) > 2 else ""
        if dataset:
            parts.append(_DATASET_LABELS.get(dataset, dataset.replace("-", " ")))
        parts.append(segments[1])
    return " · ".join(parts) or "Source (no title provided)"


def friendly_error(message: str) -> str:
    """Strip pydantic/validation dumps down to one plain sentence."""
    match = _PYDANTIC_VALUE_ERROR.search(message)
    if "validation error" in message and match:
        return match.group(1).strip()
    return message


def _first_line(value: object, limit: int = 120) -> str:
    text = str(redact_secrets(str(value or ""))).strip().splitlines()
    return (text[0] if text else "")[:limit]


def provider_notice(event: Any) -> str | None:
    """One-line OpenRouter failure notice; tolerant of missing structured fields."""
    if getattr(event, "type", None) != "provider.failed":
        return None
    reason = getattr(event, "reason", None)
    message = _first_line(getattr(event, "message", ""))
    if reason:
        label = _REASON_LABELS.get(str(reason), str(reason))
        line = f"⚠ OpenRouter error ({reason}): {label}"
        if message and message != label:
            line += f" — {message}"
    else:
        line = f"⚠ OpenRouter error: {message}"
    return sanitize_terminal_text(line)


def review_unavailable(event: Any) -> bool:
    """True when the completed event reports the independent review was skipped."""
    for holder in (event, getattr(event, "meta", None)):
        if getattr(holder, "output_review", None) == "unavailable":
            return True
    return False


def render_sources_plain(sources: list[dict[str, str]]) -> str:
    sources = dedupe_sources(sources)
    lines = [f"\nSources · {len(sources)}"]
    for index, source in enumerate(sources, 1):
        url = source.get("url", "")
        title = source_label(source)
        publisher = (
            source.get("publisher")
            or source.get("source")
            or urlparse(url).netloc
            or source.get("source_type", "")
        )
        lines.append(
            f"[{index}] {sanitize_terminal_text(title)}"
            + (f" — {sanitize_terminal_text(publisher)}" if publisher else "")
        )
        if url:
            lines.append(f"    {sanitize_terminal_text(url)}")
    return "\n".join(lines) + "\n"


def render_event(event: ResearchEvent, session_id: str | None = None) -> str:
    if event.type == "run.started":
        return f"\nYou\n{sanitize_terminal_text(event.query)}\n\nFIN-AI\n"
    if event.type == "stage.started":
        return f"\n◉ {sanitize_terminal_text(event.label)}\n"
    if event.type == "check.stage":
        label = sanitize_terminal_text(event.label)
        if event.passed:
            return f"  ✓ {label}\n"
        reasons = sanitize_terminal_text("; ".join(event.reasons[:2]))
        reasons = f" — {reasons}" if reasons else ""
        tail = (
            f", retrying ({event.attempt}/{event.max_attempts})"
            if event.retrying
            else ", using verified-evidence fallback"
        )
        return f"  ✗ {label}{reasons}{tail}\n"
    if event.type == "tool.started":
        detail = f" · {sanitize_terminal_text(event.detail)}" if event.detail else ""
        return f"  ◉ {sanitize_terminal_text(event.tool)}{detail}\n"
    if event.type == "tool.completed":
        return f"  ✓ {sanitize_terminal_text(event.tool)}\n"
    if event.type == "tool.failed":
        return f"  ✗ {sanitize_terminal_text(event.tool)}: {sanitize_terminal_text(friendly_error(event.message))}\n"
    if event.type == "response.delta":
        return sanitize_terminal_text(event.text)
    if event.type == "sources.updated":
        return render_sources_plain(event.sources)
    if event.type == "approval.requested":
        return f"\n? Approval required\n{sanitize_terminal_text(event.prompt)}\n"
    if event.type == "clarification.requested":
        session = (
            f'Session: {session_id}\nReply with: --session {session_id} "<your answer>"\n'
            if session_id
            else ""
        )
        return (
            "\nFIN-AI needs clarification\n"
            f"{sanitize_terminal_text(event.prompt)}\n{session}"
        )
    if event.type == "run.failed":
        return f"\n✗ {sanitize_terminal_text(event.category)}: {sanitize_terminal_text(friendly_error(event.message))}\n"
    if event.type == "provider.failed":
        notice = provider_notice(event)
        return f"{notice}\n" if notice else ""
    if event.type == "run.cancelled":
        return "\n✓ Cancelled\n"
    if event.type == "run.completed":
        duration = (
            f" · {event.duration_ms:.0f}ms" if event.duration_ms is not None else ""
        )
        label = {
            "partial": "Partial response",
            "insufficient_data": "Insufficient evidence",
            "completed_with_limited_evidence": "Completed with limited evidence",
        }.get(event.terminal_status, "Completed")
        artifact = (
            f"  Run artifact: {sanitize_terminal_text(event.artifact_path)}\n"
            if event.artifact_path
            else ""
        )
        note = f"  {REVIEW_UNAVAILABLE_NOTE}\n" if review_unavailable(event) else ""
        return f"\n✓ {label}{duration}\n{note}{artifact}"
    return ""


def render_plain(events: Iterable[ResearchEvent], session_id: str | None = None) -> str:
    return "".join(render_event(event, session_id) for event in events)
