"""Small, provider-independent context budget helpers."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from app.core.prompts import PromptRegistry
from app.models.request_models import Message

ROUTER_CONTEXT_MAX_TOKENS = 8_000
DEFAULT_INDIAN_BANK_PEERS = [
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
    "KOTAKBANK.NS",
    "AXISBANK.NS",
    "INDUSINDBK.NS",
    "BANKBARODA.NS",
    "CANBK.NS",
    "PNB.NS",
    "FEDERALBNK.NS",
    "IDFCFIRSTB.NS",
]
_ENTITY_STOP_WORDS = {
    "ANALYSE",
    "ANALYZE",
    "BANK",
    "CAN",
    "COMPARE",
    "COMPANY",
    "CURRENT",
    "FOR",
    "FROM",
    "HAVE",
    "LAST",
    "PRICE",
    "REPORT",
    "STOCK",
    "THE",
    "THIS",
    "WITH",
}


@dataclass(frozen=True)
class ContextBudget:
    max_tokens: int = 250_000
    compaction_ratio: float = 0.9

    @property
    def compaction_limit(self) -> int:
        return int(self.max_tokens * self.compaction_ratio)

    def should_compact(self, estimated_tokens: int) -> bool:
        return estimated_tokens >= self.compaction_limit

    def compact(
        self, messages: list[Message]
    ) -> tuple[list[Message], dict[str, int | str]]:
        """Keep the newest turns and a bounded textual summary of older turns."""
        estimated = sum(self._message_tokens(message) for message in messages)
        if not self.should_compact(estimated):
            return messages, {"estimated_tokens": estimated, "compacted_messages": 0}

        keep_budget = int(self.compaction_limit * 0.7)
        kept: list[Message] = []
        used = 0
        for message in reversed(messages):
            tokens = self._message_tokens(message)
            if kept and used + tokens > keep_budget:
                break
            kept.append(message)
            used += tokens
        kept.reverse()
        dropped = messages[: len(messages) - len(kept)]
        summary_lines = [self._summary_line(message) for message in dropped]
        compacted = [
            Message(
                role="system",
                content=PromptRegistry.bundled().render(
                    "session.compacted_history", summary="\n".join(summary_lines)
                ),
                prompt_key="session.compacted_history",
            ),
            *kept,
        ]
        source_hash = hashlib.sha256(
            json.dumps(
                [message.model_dump(mode="json") for message in dropped],
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return compacted, {
            "estimated_tokens": estimated,
            "compacted_messages": len(dropped),
            "kept_messages": len(kept),
            "source_hash": source_hash,
        }

    @staticmethod
    def estimate(text: str) -> int:
        """Conservative estimate until a model-specific tokenizer is available."""
        return (len(text) + 3) // 4

    @classmethod
    def _message_tokens(cls, message: Message) -> int:
        payload = json.dumps(message.model_dump(exclude_none=True), sort_keys=True)
        return cls.estimate(payload)

    @staticmethod
    def _summary_line(message: Message) -> str:
        details = ""
        if message.tool_calls:
            names = [
                str(call.get("function", {}).get("name") or call.get("name", "tool"))
                for call in message.tool_calls
            ]
            details = f" tool_calls={','.join(names)}"
        if message.tool_call_id:
            details += f" tool_call_id={message.tool_call_id}"
        return f"{message.role}:{details} {message.content[:500]}".strip()


def build_router_context(
    history: list[Message],
    query: str,
    *,
    resolved_ticker: str | None = None,
    instrument_resolution_status: str | None = None,
    instrument_resolution_source: str | None = None,
    instrument_candidates: list[dict[str, Any]] | None = None,
    max_tokens: int = ROUTER_CONTEXT_MAX_TOKENS,
) -> dict[str, Any]:
    """Build a small, untrusted summary for routing decisions."""
    recent_messages: list[dict[str, str]] = []
    for message in history[-12:]:
        content = message.content[:2_000]
        if message.role == "tool":
            content = f"tool output: {content[:300]}"
        recent_messages.append({"role": message.role, "content": content})

    source = " ".join(message.content for message in history[-20:])[:12_000]
    entities = _extract_entities(source)
    context: dict[str, Any] = {
        "is_follow_up": bool(history[:-1]) and _is_follow_up(query),
        "resolved_entities": entities,
        "recent_messages": recent_messages,
    }
    if resolved_ticker:
        context["resolved_ticker"] = resolved_ticker
    if instrument_resolution_status:
        context["instrument_resolution_status"] = instrument_resolution_status
    if instrument_resolution_source:
        context["instrument_resolution_source"] = instrument_resolution_source
    if instrument_candidates:
        context["instrument_candidates"] = instrument_candidates[:8]
    defaults = _research_defaults(source, query)
    context.update(defaults)
    while ContextBudget.estimate(json.dumps(context, sort_keys=True)) > max_tokens:
        if context["recent_messages"]:
            context["recent_messages"].pop(0)
        elif context["resolved_entities"]:
            context["resolved_entities"].pop()
        else:
            break
    context["estimated_tokens"] = ContextBudget.estimate(
        json.dumps(context, sort_keys=True)
    )
    return context


def _is_follow_up(query: str) -> bool:
    return bool(
        re.search(
            r"\b(this|that|it|previous|earlier|above|same|also|compare)\b",
            query,
            re.IGNORECASE,
        )
    )


def _research_defaults(source: str, query: str) -> dict[str, Any]:
    lowered = f"{source} {query}".casefold()
    comparison = bool(
        re.search(r"\b(compare|comparison|other|same sector|peer|peers)\b", lowered)
    )
    if not comparison:
        return {}
    if not re.search(r"\b(bank|banks|banking)\b", lowered):
        return {"comparison_intent": True}
    ticker = _resolve_indian_bank_ticker(lowered)
    return {
        "comparison_intent": True,
        "comparison_sector": "indian_banks",
        "resolved_ticker": ticker,
        "comparison_tickers": list(DEFAULT_INDIAN_BANK_PEERS),
        "default_timeframe": "1y",
    }


def _resolve_indian_bank_ticker(text: str) -> str | None:
    if "hdfc bank" in text or "hdfcbank" in text:
        return "HDFCBANK.NS"
    match = re.search(r"\b([a-z0-9]+\.ns)\b", text, re.IGNORECASE)
    return match.group(1).upper() if match else None


def _extract_entities(text: str) -> list[str]:
    candidates = re.findall(
        r"\b[A-Z]{2,10}(?:\.[A-Z]+)?(?:\s+[A-Z][a-z]+){0,2}\b|\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b",
        text,
    )
    entities: list[str] = []
    for candidate in candidates:
        normalized = " ".join(candidate.split())
        if normalized.upper() in _ENTITY_STOP_WORDS:
            continue
        if normalized not in entities:
            entities.append(normalized)
    return entities[:16]
