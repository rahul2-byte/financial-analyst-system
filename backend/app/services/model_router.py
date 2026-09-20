from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from app.models.request_models import Message
from app.models.routing import ModelTier, RoutePlan


@dataclass(frozen=True)
class ProviderCapabilities:
    streaming: bool = True
    tool_calls: bool = True
    structured_output: bool = False
    max_context_tokens: int = 0
    reasoning: bool = False


@dataclass(frozen=True)
class ModelBinding:
    provider: str
    model: str
    service: Any
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)


class ModelRouter:
    """Route model calls to a configured provider binding for the active plan."""

    def __init__(self, bindings: dict[ModelTier, ModelBinding]) -> None:
        self._bindings = dict(bindings)
        self._active_tier = ModelTier.MAIN
        self.last_selection: dict[str, str] = {}

    def set_route(self, route: RoutePlan) -> None:
        if route.model_tier is ModelTier.NONE:
            raise ValueError("a model router cannot execute a no-model route")
        if route.model_tier not in self._bindings:
            raise ValueError(
                f"no provider configured for tier {route.model_tier.value}"
            )
        self._active_tier = route.model_tier

    def reset_main(self) -> None:
        """Return to the safe default for the next request."""
        self._active_tier = ModelTier.MAIN

    def _binding(self) -> ModelBinding:
        binding = self._bindings.get(self._active_tier)
        if binding is None:
            raise RuntimeError(
                f"no provider configured for tier {self._active_tier.value}"
            )
        self.last_selection = {"provider": binding.provider, "model": binding.model}
        return binding

    def generate_stream(
        self, messages: list[Message], model: str, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        binding = self._binding()
        return binding.service.generate_stream(messages, binding.model, **kwargs)

    async def generate(self, messages: list[Message], model: str, **kwargs: Any) -> str:
        binding = self._binding()
        return await binding.service.generate(messages, binding.model, **kwargs)

    async def generate_message(
        self, messages: list[Message], model: str, **kwargs: Any
    ) -> Message:
        binding = self._binding()
        return await binding.service.generate_message(messages, binding.model, **kwargs)

    async def check_health(self) -> bool:
        return await self._binding().service.check_health()
