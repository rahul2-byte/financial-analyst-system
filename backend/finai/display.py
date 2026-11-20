"""Pure presentation-wording helpers shared by the bridge and plain output.

Everything here is deterministic, provider-agnostic and free of terminal-UI
imports, so the bridge can enrich each event with display-ready strings without
coupling to the interactive UI.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from app.events.models import (
    ClarificationRequested,
    ProviderCompleted,
    ProviderFailed,
    ProviderRetrying,
    ProviderStreamStarted,
    ResearchEvent,
    RunCompleted,
    RunFailed,
    SourcesUpdated,
    StageCompleted,
    StageFailed,
    StageStarted,
    ToolCompleted,
    ToolFailed,
    ToolProgress,
    ToolStarted,
)
from app.security.policy import redact_secrets

from .bridge.protocol import Display, DisplayCandidate, DisplaySource
from .safety import sanitize_terminal_text

VERBS = {
    "fetch": "Fetched",
    "get": "Fetched",
    "run": "Ran",
    "analyze": "Analyzed",
    "analyse": "Analyzed",
    "compute": "Computed",
    "search": "Searched",
    "resolve": "Resolved",
    "load": "Loaded",
    "read": "Read",
}
ACTIVE_VERBS = {
    "fetch": "Fetching",
    "get": "Fetching",
    "run": "Running",
    "analyze": "Analyzing",
    "analyse": "Analyzing",
    "compute": "Computing",
    "search": "Searching",
    "resolve": "Resolving",
    "load": "Loading",
    "read": "Reading",
}
# Short noun used for failures and the collapsed summary ("news unavailable").
NOUNS = {
    "fetch_fundamentals": "fundamentals",
    "get_technical_overview": "technical overview",
    "fetch_news": "news",
    "run_fundamental_scan": "fundamental scan",
    "fetch_price_history": "price history",
}
KV = re.compile(r"(\w+)=([^,\s]+)")
RAW_ID = re.compile(r"\b[a-z_]+:[a-z_]+\b")
QUOTE_SYMBOL = re.compile(r"/quote/([A-Z0-9&_-]+\.(?:NS|BO))", re.IGNORECASE)
CANDIDATE = re.compile(
    r"^\s*[-*•]\s*(?:(?P<sym>[A-Z0-9&.\-]+)\s*\((?P<ex1>[A-Z]+)\)\s*(?P<name1>.*)"
    r"|(?P<name2>.+?)\s*\((?P<sym2>[A-Z0-9&.\-]+)(?:,\s*(?P<ex2>[A-Z]+))?\))\s*$"
)
ACRONYMS = {"HDFC", "ICICI", "SBI", "LIC", "TCS", "ITC", "NTPC", "ONGC", "IDBI", "UPL"}

PROVIDER_LABELS = {
    "yfinance": "Yahoo Finance",
    "yahoo": "Yahoo Finance",
    "upstox": "Upstox",
    "tinyfish": "TinyFish news",
}
DATASET_LABELS = {
    "history": "price history",
    "financials": "financials",
    "key-statistics": "key statistics",
    "news": "news",
}
REASON_LABELS = {
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
PYDANTIC_VALUE_ERROR = re.compile(r"Value error, (.*?)(?: \[type=|\n|$)")


def clean_text(value: str) -> str:
    """Strip terminal escapes and control characters from runtime text."""
    return sanitize_terminal_text(value)


def tool_name(label: str) -> str:
    return label.split(":", 1)[-1].strip()


def noun(label: str) -> str:
    name = tool_name(label)
    if name in NOUNS:
        return NOUNS[name]
    words = name.replace("_", " ").split()
    if len(words) > 1 and words[0] in VERBS:
        words = words[1:]
    return " ".join(words) or label


def tool_label(label: str, *, active: bool = False) -> str:
    """`data:fetch_stock_data` -> `Fetched stock data` (never a raw id).

    ``active`` gives the in-progress form (`Fetching stock data`) for a tool
    that is still running.
    """
    words = tool_name(label).replace("_", " ").split()
    if not words:
        return label
    verb = (ACTIVE_VERBS if active else VERBS).get(words[0])
    text = " ".join([verb, *words[1:]] if verb else words)
    return text[:1].upper() + text[1:]


def _raw_id_free(text: str, label: str = "") -> str:
    """Remove raw tool ids; a detail that is only the tool name is empty."""
    cleaned = clean_text(text)
    stripped = " ".join(RAW_ID.sub("", cleaned).split()).strip(" :·")
    if stripped.lower() in {
        "",
        "running",
        noun(label).lower(),
        tool_name(label).lower(),
    }:
        return ""
    named = RAW_ID.sub(lambda match: noun(match.group(0)), cleaned)
    return " ".join(named.split()).strip(" :·")


def tool_detail(label: str, detail: str | None) -> str:
    """Short human detail; never raw key=value dumps, JSON or raw tool ids."""
    detail = (detail or "").strip()
    if not detail or detail.startswith(("{", "[")):
        return ""
    if detail.startswith("key values:"):
        pairs = dict(KV.findall(detail))
        if label.endswith("get_technical_overview") and "close" in pairs:
            return f"close ₹{pairs['close']}"
        return ""
    if "=" in detail:
        return ""
    text = clean_text(detail)
    if RAW_ID.search(text):
        text = _raw_id_free(text, label)
    return short(text, 40)


def failure_detail(label: str, detail: str | None) -> str:
    text = (detail or "").strip().lower()
    if not text or "no usable" in text or "unavailable" in text:
        return (
            "no usable articles"
            if tool_name(label) == "fetch_news"
            else "no usable data"
        )
    return short(RAW_ID.sub("", clean_text(text)).strip(" :·"), 40)


def short(text: str, limit: int = 72) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def failed_nouns(activities: Mapping[str, Any]) -> list[str]:
    nouns: list[str] = []
    for key, activity in activities.items():
        if key.startswith("tool:") and activity.status == "failed":
            value = noun(activity.label)
            if value not in nouns:
                nouns.append(value)
    return nouns


def instrument_from_sources(sources: list[dict[str, str]]) -> str | None:
    """Best-effort resolved instrument (e.g. HDFCBANK.NS) from provider quote URLs."""
    for source in sources:
        match = QUOTE_SYMBOL.search(source.get("url", ""))
        if match:
            return match.group(1).upper()
    return None


def has_tool_trail(activities: Mapping[str, Any]) -> bool:
    return any(key.startswith("tool:") for key in activities)


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
    provider = PROVIDER_LABELS.get(raw.lower(), raw)
    parts = [provider] if provider else []
    segments = [
        part for part in urlparse(source.get("url", "")).path.split("/") if part
    ]
    if len(segments) >= 2 and segments[0] == "quote":
        dataset = segments[2] if len(segments) > 2 else ""
        if dataset:
            parts.append(DATASET_LABELS.get(dataset, dataset.replace("-", " ")))
        parts.append(segments[1])
    return " · ".join(parts) or "Source (no title provided)"


def first_line(value: object, limit: int = 120) -> str:
    text = str(redact_secrets(str(value or ""))).strip().splitlines()
    return (text[0] if text else "")[:limit]


def tool_failure_text(message: str, tool: str) -> str:
    """Friendly, raw-id-free text for a failed tool (shared by state and display)."""
    return _raw_id_free(friendly_error(message), tool)


def friendly_error(message: str) -> str:
    """Strip pydantic/validation dumps down to one plain sentence."""
    match = PYDANTIC_VALUE_ERROR.search(message)
    if "validation error" in message and match:
        return match.group(1).strip()
    return message


def provider_notice(event: Any) -> str | None:
    """One-line OpenRouter failure notice; tolerant of missing structured fields."""
    if getattr(event, "type", None) != "provider.failed":
        return None
    reason = getattr(event, "reason", None)
    message = first_line(getattr(event, "message", ""))
    if reason:
        label = REASON_LABELS.get(str(reason), str(reason))
        line = f"⚠ OpenRouter error ({reason}): {label}"
        if message and message != label:
            line += f" — {message}"
    else:
        line = f"⚠ OpenRouter error: {message}"
    return clean_text(line)


def review_unavailable(event: Any) -> bool:
    """True when the completed event reports the independent review was skipped."""
    for holder in (event, getattr(event, "meta", None)):
        if getattr(holder, "output_review", None) == "unavailable":
            return True
    return False


def provider_retrying_detail(reason: str, delay_ms: float) -> str:
    return f"{reason} · {delay_ms / 1000:.1f}s"


def provider_stream_detail(first_byte_ms: float) -> str:
    return f"first byte {first_byte_ms / 1000:.1f}s"


def provider_completed_detail(attempts: int, duration_ms: float) -> str:
    return f"{attempts} attempt(s) · {duration_ms / 1000:.1f}s"


def title_name(name: str) -> str:
    """`HDFC BANK LTD` -> `HDFC Bank Ltd`; already-mixed-case names are kept."""
    if not name.isupper():
        return name
    words = []
    for word in name.split():
        if word in ACRONYMS:
            words.append(word)
        else:
            words.append(word.capitalize())
    return " ".join(words)


def match_candidate(line: str) -> tuple[str, str, str] | None:
    match = CANDIDATE.match(line)
    if not match:
        return None
    symbol = match["sym"] or match["sym2"]
    name = (match["name1"] or match["name2"] or "").strip()
    exchange = match["ex1"] or match["ex2"] or ""
    return symbol, title_name(name), exchange


def parse_clarification(prompt: str) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Split a clarification prompt into candidates and passthrough lines."""
    candidates: list[tuple[str, str, str]] = []
    other_lines: list[str] = []
    for line in clean_text(prompt).splitlines():
        candidate = match_candidate(line)
        if candidate is None:
            other_lines.append(line)
        else:
            candidates.append(candidate)
    return candidates, other_lines


def _display_sources(sources: list[dict[str, str]]) -> list[DisplaySource]:
    rows: list[DisplaySource] = []
    for source in dedupe_sources(sources):
        title = clean_text(source_label(source))
        url = clean_text(source.get("url", ""))
        host: str | None = None
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            host = parsed.netloc
        if host and host.removeprefix("www.") == title.removeprefix("www."):
            host = None
        rows.append(DisplaySource(label=title, url=url, host=host))
    return rows


def _tool_display(event: ResearchEvent) -> Display:
    active = isinstance(event, ToolStarted | ToolProgress)
    label = clean_text(tool_label(event.tool, active=active))
    display = Display(
        label=label,
        noun=clean_text(noun(event.tool)),
        detail=None,
        failure_detail=None,
        friendly=None,
    )
    if isinstance(event, ToolFailed):
        display.detail = clean_text(tool_detail(event.tool, event.message)) or None
        display.failure_detail = (
            clean_text(failure_detail(event.tool, event.message)) or None
        )
        display.friendly = tool_failure_text(event.message, event.tool)
    elif isinstance(event, ToolProgress):
        display.detail = clean_text(tool_detail(event.tool, event.message)) or None
    elif isinstance(event, ToolStarted | ToolCompleted):
        display.detail = clean_text(tool_detail(event.tool, event.detail)) or None
    return display


def build_display(event: ResearchEvent, run_state: Any) -> Display | None:
    """Build the bridge ``Display`` payload for one event.

    ``run_state`` is the presentation state *after* this event is reduced.
    Returns ``None`` for event types that have no display row.
    """
    if isinstance(event, ToolStarted | ToolCompleted | ToolFailed | ToolProgress):
        return _tool_display(event)

    if isinstance(event, StageStarted):
        return Display(label=clean_text(event.label))
    if isinstance(event, StageCompleted):
        return Display(
            label=clean_text(event.label),
            detail=clean_text(event.detail) if event.detail else None,
        )
    if isinstance(event, StageFailed):
        return Display(
            label=clean_text(event.label),
            detail=clean_text(event.message) or None,
            friendly=clean_text(friendly_error(event.message)),
        )

    if isinstance(event, ProviderFailed):
        return Display(
            notice=provider_notice(event),
            friendly=clean_text(friendly_error(event.message)),
        )
    if isinstance(event, ProviderRetrying):
        return Display(
            detail=clean_text(provider_retrying_detail(event.reason, event.delay_ms))
        )
    if isinstance(event, ProviderStreamStarted):
        return Display(detail=clean_text(provider_stream_detail(event.first_byte_ms)))
    if isinstance(event, ProviderCompleted):
        return Display(
            detail=clean_text(
                provider_completed_detail(event.attempts, event.duration_ms)
            )
        )

    if isinstance(event, RunFailed):
        return Display(friendly=clean_text(friendly_error(event.message)))

    if isinstance(event, SourcesUpdated):
        return Display(sources=_display_sources(event.sources))

    if isinstance(event, ClarificationRequested):
        candidates, other_lines = parse_clarification(event.prompt)
        return Display(
            candidates=[
                DisplayCandidate(
                    symbol=clean_text(symbol),
                    name=clean_text(name),
                    exchange=clean_text(exchange),
                )
                for symbol, name, exchange in candidates
            ],
            lines=[clean_text(line) for line in other_lines],
        )

    if isinstance(event, RunCompleted):
        unavailable = review_unavailable(event)
        return Display(
            review_unavailable=unavailable,
            review_note=REVIEW_UNAVAILABLE_NOTE if unavailable else None,
            instrument=instrument_from_sources(run_state.sources),
            failed_nouns=failed_nouns(run_state.activities),
        )

    return None
