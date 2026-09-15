"""Small, provider-independent context budget helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.models.request_models import Message


@dataclass(frozen=True)
class ContextBudget:
    max_tokens: int = 250_000
    compaction_ratio: float = 0.9

    @property
    def compaction_limit(self) -> int:
        return int(self.max_tokens * self.compaction_ratio)

    def should_compact(self, estimated_tokens: int) -> bool:
        return estimated_tokens >= self.compaction_limit

    def compact(self, messages: list[Message]) -> tuple[list[Message], dict[str, int | str]]:
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
        summary_lines = [
            "Earlier FIN-AI conversation context (compacted):",
            *(
                self._summary_line(message)
                for message in dropped
            ),
        ]
        compacted = [
            Message(role="system", content="\n".join(summary_lines)),
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
