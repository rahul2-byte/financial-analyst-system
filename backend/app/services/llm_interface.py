from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Dict, Any
from app.models.request_models import Message


class LLMServiceInterface(ABC):
    @abstractmethod
    def generate_stream(
        self, messages: List[Message], model: str, **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Generates a stream of responses from the LLM.
        Returns an AsyncGenerator.
        """
        pass

    @abstractmethod
    async def generate(self, messages: List[Message], model: str, **kwargs) -> str:
        """
        Generates a complete response from the LLM.
        """
        pass

    @abstractmethod
    async def generate_message(
        self, messages: List[Message], model: str, **kwargs
    ) -> Message:
        """
        Generates a complete message object from the LLM (useful for tool calls).
        """
        pass

    @abstractmethod
    async def check_health(self) -> bool:
        """
        Checks if the LLM service is available.
        """
        pass
