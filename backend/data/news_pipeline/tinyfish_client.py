from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.observability.provider_archive import ProviderArchive, ProviderSnapshot


class TinyFishSearchClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.search.tinyfish.ai",
        timeout: float = 20.0,
        client_factory: Callable[[float], Any] | None = None,
        archive: ProviderArchive | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client_factory = client_factory or self._default_client_factory
        self.archive = archive
        self.last_snapshot_hash: str | None = None

    def _default_client_factory(self, timeout: float) -> Any:
        import httpx

        return httpx.AsyncClient(timeout=timeout)

    async def search(
        self,
        *,
        query: str,
        num_results: int,
        start_published_date: datetime,
    ) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        params = {
            "query": query,
            "limit": num_results,
            "domain_type": "news",
            "after_date": start_published_date.date().isoformat(),
        }
        async with self.client_factory(self.timeout) as client:
            response = await client.get(
                self.base_url,
                headers={"X-API-Key": self.api_key},
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
        if self.archive is not None:
            snapshot = self.archive.store(
                ProviderSnapshot(
                    provider="tinyfish",
                    operation="news_search",
                    payload=payload,
                    fetched_at=datetime.now().astimezone(),
                )
            )
            self.last_snapshot_hash = snapshot.content_hash
        return [item for item in payload.get("results", []) if isinstance(item, dict)]
