"""Explicit runtime-owned external services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.prompts import PromptRegistry
from app.core.skills import SkillRegistry
from app.observability.provider_archive import ProviderArchive
from app.services.routing_policy import RoutingPolicy


@dataclass
class RuntimeResources:
    """Services shared by one runtime instance."""

    llm_service: Any
    yf_fetcher: Any
    provider_archive: ProviderArchive | None = None
    upstox_fetcher: Any | None = None
    news_pipeline_runner: Any | None = None
    routing_policy: RoutingPolicy | None = None
    prompts: PromptRegistry | None = None
    skills: SkillRegistry | None = None


def build_runtime_resources(
    *,
    llm_service: Any | None = None,
    yf_fetcher: Any | None = None,
    provider_archive: ProviderArchive | None = None,
    replay_snapshots: dict[str, Any] | None = None,
    source_quality_filtering: bool = True,
) -> RuntimeResources:
    """Build runtime dependencies, allowing tests to inject fakes."""
    prompts = PromptRegistry.bundled()
    skills = SkillRegistry.bundled()
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
            routing_policy=RoutingPolicy(jev=None),
            prompts=prompts,
            skills=skills,
        )
    if llm_service is None:
        from app.services.hive_service import HiveService

        hive_service = HiveService(provider_archive=archive)
        llm_service = hive_service
        if (
            settings.FINAI_CHATGPT_CODEX_ENABLED
            and settings.FINAI_CHATGPT_CODEX_PRIMARY
        ):
            from app.services.chatgpt_codex_service import (
                ChatGPTCodexService,
                CodexCredentialStore,
            )

            llm_service = ChatGPTCodexService(
                fallback=hive_service,
                credential_store=CodexCredentialStore(
                    Path(settings.FINAI_CHATGPT_CODEX_CREDENTIAL_PATH).expanduser()
                ),
                client_id=settings.FINAI_CHATGPT_CODEX_CLIENT_ID,
                issuer=settings.FINAI_CHATGPT_CODEX_ISSUER,
                endpoint=settings.FINAI_CHATGPT_CODEX_API_ENDPOINT,
                timeout_seconds=settings.FINAI_CHATGPT_CODEX_TIMEOUT_SECONDS,
                fallback_model=settings.HIVE_MODEL,
            )
    if yf_fetcher is None:
        from data.providers.yfinance import YFinanceFetcher

        yf_fetcher = YFinanceFetcher()
    if settings.UPSTOX_ACCESS_TOKEN:
        from data.providers.upstox import UpstoxFetcher

        upstox_fetcher = UpstoxFetcher()
    else:
        upstox_fetcher = None
    from data.news_pipeline.runner import NewsPipelineRunner

    jev = None
    if settings.FINAI_ROUTER_ENABLED:
        from app.services.jev_service import JevService

        jev = JevService(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_JEV_BASE_URL,
            model=settings.OPENROUTER_JEV_MODEL,
            timeout_seconds=settings.FINAI_ROUTER_TIMEOUT_SECONDS,
            max_retries=settings.FINAI_ROUTER_MAX_RETRIES,
            prompts=prompts,
        )

    return RuntimeResources(
        llm_service=llm_service,
        yf_fetcher=yf_fetcher,
        provider_archive=archive,
        upstox_fetcher=upstox_fetcher,
        news_pipeline_runner=NewsPipelineRunner(),
        routing_policy=RoutingPolicy(
            jev=jev, min_confidence=settings.FINAI_ROUTER_MIN_CONFIDENCE
        ),
        prompts=prompts,
        skills=skills,
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
