import logging
from typing import List, Dict, Any
from collections import deque

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Manages conversation history with sliding window."""

    def __init__(self, max_history: int = 10):
        self.max_history = max_history
        self.messages: deque = deque(maxlen=max_history)

    def add(self, role: str, content: str) -> None:
        """Add a message to memory."""
        self.messages.append({"role": role, "content": content})

    def get_history(self) -> List[Dict[str, str]]:
        """Get full conversation history."""
        return list(self.messages)

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()


def memory_reducer(
    left: List[Dict[str, str]], right: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    """LangGraph reducer for conversation history with truncation."""
    combined = list(left) + list(right)
    max_history = 10
    if len(combined) > max_history:
        return combined[-max_history:]
    return combined
