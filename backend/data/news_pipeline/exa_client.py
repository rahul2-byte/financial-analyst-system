from __future__ import annotations

from datetime import datetime
from typing import Any, Callable


class ExaSearchClient:
    def __init__(
        self,
        *,
        api_key: str,
        client_factory: Callable[[str], Any] | None = None,
        use_text_content: bool = True,
    ) -> None:
        self.api_key = api_key
        self.client_factory = client_factory or self._default_client_factory
        self.use_text_content = use_text_content
        self._client: Any | None = None

    def _default_client_factory(self, api_key: str) -> Any:
        from exa_py import Exa

        return Exa(api_key)

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self.client_factory(self.api_key)
        return self._client

    async def search(
        self,
        *,
        query: str,
        num_results: int,
        start_published_date: datetime,
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "num_results": num_results,
            "category": "news",
            "start_published_date": start_published_date.isoformat(),
        }
        if self.use_text_content:
            kwargs["text"] = {"max_characters": 4000}

        response = self.client.search_and_contents(query, **kwargs)
        return list(getattr(response, "results", []) or [])
