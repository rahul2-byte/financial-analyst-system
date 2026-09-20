from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from app.models.request_models import Message
from app.models.routing import ModelTier, RoutePlan
from app.services.model_router import ModelBinding, ModelRouter, ProviderCapabilities


class FakeProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[str] = []

    def generate_stream(
        self, messages: list[Message], model: str, **kwargs: object
    ) -> AsyncGenerator[dict[str, object], None]:
        async def stream() -> AsyncGenerator[dict[str, object], None]:
            self.calls.append(f"stream:{model}")
            yield {"event": "done", "data": "[DONE]"}

        return stream()

    async def generate(
        self, messages: list[Message], model: str, **kwargs: object
    ) -> str:
        self.calls.append(f"generate:{model}")
        return self.name

    async def generate_message(
        self, messages: list[Message], model: str, **kwargs: object
    ) -> Message:
        self.calls.append(f"message:{model}")
        return Message(role="assistant", content=self.name)

    async def check_health(self) -> bool:
        return True


def test_model_router_delegates_to_route_tier() -> None:
    main = FakeProvider("main")
    small = FakeProvider("small")
    router = ModelRouter(
        {
            ModelTier.MAIN: ModelBinding(
                provider="hive", model="main-model", service=main
            ),
            ModelTier.SMALL: ModelBinding(
                provider="local", model="small-model", service=small
            ),
        }
    )
    router.set_route(RoutePlan(model_tier=ModelTier.SMALL, allowed_tools=set()))

    result = asyncio.run(router.generate([], "reasoning"))

    assert result == "small"
    assert small.calls == ["generate:small-model"]
    assert main.calls == []
    assert router.last_selection == {"provider": "local", "model": "small-model"}


def test_provider_capabilities_are_explicit() -> None:
    capabilities = ProviderCapabilities(
        streaming=True,
        tool_calls=True,
        structured_output=True,
        max_context_tokens=32_000,
    )

    assert capabilities.tool_calls is True
    assert capabilities.max_context_tokens == 32_000


def test_model_router_can_reset_after_route_failure() -> None:
    main = FakeProvider("main")
    router = ModelRouter(
        {
            ModelTier.MAIN: ModelBinding(provider="hive", model="main", service=main),
        }
    )
    router.reset_main()

    result = asyncio.run(router.generate([], "reasoning"))

    assert result == "main"
