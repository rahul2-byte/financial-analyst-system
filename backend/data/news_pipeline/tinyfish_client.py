from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.quota import RequestQuota
from app.observability.provider_archive import ProviderArchive, ProviderSnapshot
from data.retry import ProviderUnavailable, acall_with_retry, provider_retry_kwargs


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
        self._shared_client: Any | None = None
        self._shared_users = 0
        self.quota = RequestQuota(
            Path(settings.FINAI_QUOTA_DB),
            per_second=settings.FINAI_PROVIDER_REQUESTS_PER_SECOND,
        )

    def _default_client_factory(self, timeout: float) -> Any:
        import httpx

        return httpx.AsyncClient(timeout=timeout)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[None]:
        """Reuse one HTTP client (one TCP/TLS handshake) for searches inside.

        Re-entrant: nested or concurrent sessions share the outermost client.
        Outside a session, each search opens its own client as before.
        """
        if self._shared_client is not None:
            self._shared_users += 1
            try:
                yield
            finally:
                self._shared_users -= 1
            return
        async with self.client_factory(self.timeout) as client:
            self._shared_client = client
            self._shared_users = 1
            try:
                yield
            finally:
                self._shared_users -= 1
                self._shared_client = None

    async def search(
        self,
        *,
        query: str,
        num_results: int,
        start_published_date: datetime,
    ) -> list[dict[str, Any]]:
        if not self.api_key:
            # Must read as "news unavailable", never as "no news".
            raise ProviderUnavailable("tinyfish", "api_key_missing")
        params = {
            "query": query,
            "limit": num_results,
            "domain_type": "news",
            "after_date": start_published_date.date().isoformat(),
        }

        async def send(client: Any) -> Any:
            # Waits for a free slot so concurrent queries never trip the limit.
            await self.quota.acquire("tinyfish")
            response = await client.get(
                self.base_url,
                headers={"X-API-Key": self.api_key},
                params=params,
            )
            response.raise_for_status()
            return response.json()

        async def request() -> Any:
            if self._shared_client is not None:
                return await send(self._shared_client)
            async with self.client_factory(self.timeout) as client:
                return await send(client)

        payload = await acall_with_retry(
            request, provider="tinyfish", **provider_retry_kwargs()
        )
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
