"""Explicit runtime-owned external services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings
from app.models.routing import ModelTier
from app.observability.provider_archive import ProviderArchive
from app.services.model_router import ModelBinding, ModelRouter, ProviderCapabilities
from app.services.routing_policy import RoutingPolicy


@dataclass
class RuntimeResources:
    """Services shared by one runtime instance."""

    llm_service: Any
    yf_fetcher: Any
    provider_archive: ProviderArchive | None = None
    upstox_fetcher: Any | None = None
    news_pipeline_runner: Any | None = None
    model_router: ModelRouter | None = None
    routing_policy: RoutingPolicy | None = None


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
            model_router=None,
            routing_policy=RoutingPolicy(jev=None),
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

    jev = None
    if settings.FINAI_ROUTER_ENABLED:
        from app.services.jev_service import JevService

        jev = JevService(
            api_key=settings.TYPESAFE_API_KEY,
            base_url=settings.TYPESAFE_BASE_URL,
            model=settings.TYPESAFE_MODEL,
            timeout_seconds=settings.FINAI_ROUTER_TIMEOUT_SECONDS,
            max_retries=settings.FINAI_ROUTER_MAX_RETRIES,
        )
    model_router = ModelRouter(_model_bindings(llm_service, archive))

    return RuntimeResources(
        llm_service=llm_service,
        yf_fetcher=yf_fetcher,
        provider_archive=archive,
        upstox_fetcher=upstox_fetcher,
        news_pipeline_runner=NewsPipelineRunner(),
        model_router=model_router,
        routing_policy=RoutingPolicy(
            jev=jev, min_confidence=settings.FINAI_ROUTER_MIN_CONFIDENCE
        ),
    )


def _model_bindings(
    llm_service: Any, archive: ProviderArchive
) -> dict[ModelTier, ModelBinding]:
    bindings: dict[ModelTier, ModelBinding] = {
        ModelTier.MAIN: ModelBinding(
            provider="hive",
            model=str(settings.HIVE_MODEL),
            service=llm_service,
            capabilities=ProviderCapabilities(
                streaming=True,
                tool_calls=True,
                structured_output=True,
                max_context_tokens=settings.FINAI_CONTEXT_MAX_TOKENS,
                reasoning=True,
            ),
        )
    }
    from app.services.openai_compatible_service import OpenAICompatibleService

    if settings.OPENAI_API_KEY:
        service = OpenAICompatibleService(
            provider_name="openai",
            base_url=settings.OPENAI_BASE_URL,
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
            provider_archive=archive,
        )
        bindings[ModelTier.MID] = ModelBinding(
            provider="openai",
            model=settings.OPENAI_MODEL,
            service=service,
            capabilities=ProviderCapabilities(
                streaming=True,
                tool_calls=True,
                structured_output=True,
                max_context_tokens=settings.FINAI_CONTEXT_MAX_TOKENS,
            ),
        )
    elif settings.ANTHROPIC_API_KEY:
        from app.services.anthropic_service import AnthropicService

        service = AnthropicService(
            api_key=settings.ANTHROPIC_API_KEY,
            base_url=settings.ANTHROPIC_BASE_URL,
            model=settings.ANTHROPIC_MODEL,
        )
        bindings[ModelTier.MID] = ModelBinding(
            provider="anthropic",
            model=settings.ANTHROPIC_MODEL,
            service=service,
            capabilities=ProviderCapabilities(
                streaming=True,
                tool_calls=False,
                structured_output=False,
                max_context_tokens=settings.FINAI_CONTEXT_MAX_TOKENS,
            ),
        )
    if settings.LOCAL_MODEL_BASE_URL:
        service = OpenAICompatibleService(
            provider_name="local_model",
            base_url=settings.LOCAL_MODEL_BASE_URL,
            api_key=settings.LOCAL_MODEL_API_KEY,
            model=settings.LOCAL_MODEL,
            provider_archive=archive,
        )
        bindings[ModelTier.SMALL] = ModelBinding(
            provider="local_model",
            model=settings.LOCAL_MODEL,
            service=service,
            capabilities=ProviderCapabilities(
                streaming=True,
                tool_calls=True,
                structured_output=True,
                max_context_tokens=settings.FINAI_CONTEXT_MAX_TOKENS,
            ),
        )
    return bindings


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
