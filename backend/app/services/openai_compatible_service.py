from __future__ import annotations

import httpx
from app.observability.provider_archive import ProviderArchive
from app.services.hive_service import HiveRetryPolicy, HiveService


class OpenAICompatibleService(HiveService):
    """Reuse the bounded streaming client for OpenAI-compatible endpoints."""

    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key: str | None,
        model: str,
        client: httpx.AsyncClient | None = None,
        retry_policy: HiveRetryPolicy | None = None,
        provider_archive: ProviderArchive | None = None,
    ) -> None:
        super().__init__(
            client,
            provider_name=provider_name,
            base_url=base_url,
            api_key=api_key,
            default_model=model,
            retry_policy=retry_policy,
            provider_archive=provider_archive,
        )
