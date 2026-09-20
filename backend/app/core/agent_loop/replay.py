"""Strict archived model stream used for offline replay."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.observability.provider_archive import ProviderArchive


class ReplayModelStream:
    """Return recorded model events and never construct a network client."""

    def __init__(self, archive: ProviderArchive, content_hash: str | list[str]) -> None:
        self._archive = archive
        self._content_hashes = (
            [content_hash] if isinstance(content_hash, str) else content_hash
        )
        self._index = 0

    def generate_stream(
        self, messages: list[Any], model: str, **kwargs: Any
    ) -> AsyncIterator[dict[str, Any]]:
        del messages, model, kwargs
        if self._index >= len(self._content_hashes):
            raise RuntimeError("replay model stream exhausted")
        content_hash = self._content_hashes[self._index]
        self._index += 1
        snapshot = self._archive.load(content_hash)
        if snapshot.operation != "model_stream" or not isinstance(
            snapshot.payload, list
        ):
            raise RuntimeError("replay snapshot does not contain a model stream")

        async def stream() -> AsyncIterator[dict[str, Any]]:
            for event in snapshot.payload:
                if not isinstance(event, dict):
                    raise TypeError("replay snapshot contains an invalid model event")
                yield event

        return stream()

    async def aclose(self) -> None:
        return None
