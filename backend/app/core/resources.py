"""Explicit runtime-owned external services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings
from app.observability.provider_archive import ProviderArchive


@dataclass
class RuntimeResources:
    """Services shared by one runtime instance."""

    llm_service: Any
    yf_fetcher: Any
    provider_archive: ProviderArchive | None = None
    upstox_fetcher: Any | None = None


def build_runtime_resources(
    *,
    llm_service: Any | None = None,
    yf_fetcher: Any | None = None,
    provider_archive: ProviderArchive | None = None,
    replay_snapshots: dict[str, str | None] | None = None,
) -> RuntimeResources:
    """Build runtime dependencies, allowing tests to inject fakes."""
    archive = provider_archive or ProviderArchive(Path(".finai"))
    if replay_snapshots:
        from app.core.agent_loop.replay import ReplayModelStream
        from data.providers.yfinance import ReplayYFinanceFetcher

        model_hash = replay_snapshots.get("model_stream")
        if not model_hash:
            raise ValueError("replay mode requires a model_stream snapshot")
        if llm_service is not None or yf_fetcher is not None:
            raise ValueError("replay mode cannot combine live provider instances")
        return RuntimeResources(
            llm_service=ReplayModelStream(archive, model_hash),
            yf_fetcher=ReplayYFinanceFetcher(
                archive,
                {key: value for key, value in replay_snapshots.items() if value},
            ),
            provider_archive=archive,
        )
    if llm_service is None:
        from app.services.hive_service import HiveService

        llm_service = HiveService(provider_archive=archive)
    if yf_fetcher is None:
        from data.providers.yfinance import YFinanceFetcher

        yf_fetcher = YFinanceFetcher()
    if settings.UPSTOX_ACCESS_TOKEN:
        from data.providers.upstox import UpstoxFetcher

        upstox_fetcher = UpstoxFetcher()
    else:
        upstox_fetcher = None
    return RuntimeResources(
        llm_service=llm_service,
        yf_fetcher=yf_fetcher,
        provider_archive=archive,
        upstox_fetcher=upstox_fetcher,
    )
