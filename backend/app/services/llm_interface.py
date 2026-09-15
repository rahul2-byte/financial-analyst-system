from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from app.models.request_models import Message


class LLMServiceInterface(ABC):
    @abstractmethod
    def generate_stream(
        self, messages: list[Message], model: str, **kwargs
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Generates a stream of responses from the LLM.
        Returns an AsyncGenerator.
        """

    @abstractmethod
    async def generate(self, messages: list[Message], model: str, **kwargs) -> str:
        """
        Generates a complete response from the LLM.
        """

    @abstractmethod
    async def generate_message(
        self, messages: list[Message], model: str, **kwargs
    ) -> Message:
        """
        Generates a complete message object from the LLM (useful for tool calls).
        """

    @abstractmethod
    async def check_health(self) -> bool:
        """
        Checks if the LLM service is available.
        """
