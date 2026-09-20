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
    news_pipeline_runner: Any | None = None


def build_runtime_resources(
    *,
    llm_service: Any | None = None,
    yf_fetcher: Any | None = None,
    provider_archive: ProviderArchive | None = None,
    replay_snapshots: dict[str, Any] | None = None,
    source_quality_filtering: bool = True,
) -> RuntimeResources:
    """Build runtime dependencies, allowing tests to inject fakes."""
    archive = provider_archive or ProviderArchive(Path(".finai"))
    if replay_snapshots:
        from app.core.agent_loop.replay import ReplayModelStream
        from data.providers.yfinance import ReplayYFinanceFetcher

        model_hashes = replay_snapshots.get("model_streams") or replay_snapshots.get(
            "model_stream"
        )
        if not model_hashes:
            raise ValueError("replay mode requires a model_stream snapshot")
        if llm_service is not None or yf_fetcher is not None:
            raise ValueError("replay mode cannot combine live provider instances")
        return RuntimeResources(
            llm_service=ReplayModelStream(archive, model_hashes),
            yf_fetcher=ReplayYFinanceFetcher(
                archive,
                {
                    key: value
                    for key, value in replay_snapshots.items()
                    if key in {"fetch_stock_price", "fetch_fundamentals"}
                    and isinstance(value, str)
                },
            ),
            provider_archive=archive,
            news_pipeline_runner=_build_replay_news_runner(
                archive,
                replay_snapshots,
                source_quality_filtering=source_quality_filtering,
            ),
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
    from data.news_pipeline.runner import NewsPipelineRunner

    return RuntimeResources(
        llm_service=llm_service,
        yf_fetcher=yf_fetcher,
        provider_archive=archive,
        upstox_fetcher=upstox_fetcher,
        news_pipeline_runner=NewsPipelineRunner(),
    )


def _build_replay_news_runner(
    archive: ProviderArchive,
    replay_snapshots: dict[str, Any],
    *,
    source_quality_filtering: bool,
) -> Any:
    from data.news_pipeline.replay import ReplayArticleExtractor, ReplayNewsConnector
    from data.news_pipeline.runner import NewsPipelineRunner

    connector = ReplayNewsConnector(
        archive,
        replay_snapshots.get("fetch_news")
        if isinstance(replay_snapshots.get("fetch_news"), str)
        else None,
    )
    return NewsPipelineRunner(
        connectors=[connector],
        extractor=ReplayArticleExtractor(connector.article_text_by_url),
        apply_quality_filter=source_quality_filtering,
    )
