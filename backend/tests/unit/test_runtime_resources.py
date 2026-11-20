from datetime import UTC, datetime

import pytest
from app.config import settings
from app.core.resources import MissingOpenRouterKeyError, build_runtime_resources
from app.observability.provider_archive import ProviderArchive, ProviderSnapshot
from app.services.openrouter_service import OpenRouterService
from data.providers.yfinance import ReplayYFinanceFetcher


def test_resource_builder_uses_strict_replay_fetcher_when_snapshot_map_is_supplied(
    tmp_path,
) -> None:
    archive = ProviderArchive(tmp_path)
    snapshot = archive.store(
        ProviderSnapshot(
            provider="yfinance",
            operation="fetch_stock_price",
            payload={"data": []},
            fetched_at=datetime(2026, 9, 18, tzinfo=UTC),
        )
    )
    model = archive.store(
        ProviderSnapshot(
            provider="openrouter",
            operation="model_stream",
            payload=[{"event": "token", "data": "replayed"}],
            fetched_at=datetime(2026, 9, 18, tzinfo=UTC),
        )
    )

    resources = build_runtime_resources(
        provider_archive=archive,
        replay_snapshots={
            "model_stream": model.content_hash,
            "fetch_stock_price": snapshot.content_hash,
        },
    )

    assert isinstance(resources.yf_fetcher, ReplayYFinanceFetcher)


def test_resource_builder_enables_upstox_when_a_token_is_configured(
    monkeypatch,
) -> None:
    class FakeUpstoxFetcher:
        pass

    monkeypatch.setattr(settings, "UPSTOX_ACCESS_TOKEN", "test-token")
    monkeypatch.setattr("data.providers.upstox.UpstoxFetcher", FakeUpstoxFetcher)

    resources = build_runtime_resources(llm_service=object(), yf_fetcher=object())

    assert isinstance(resources.upstox_fetcher, FakeUpstoxFetcher)


def test_resource_builder_uses_openrouter_as_only_llm(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "test-key")

    resources = build_runtime_resources(llm_service=None, yf_fetcher=object())

    assert isinstance(resources.llm_service, OpenRouterService)
    assert resources.llm_service.provider_name == "openrouter"


def test_resource_builder_fails_fast_without_openrouter_key(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", None)

    with pytest.raises(
        MissingOpenRouterKeyError, match="OPENROUTER_API_KEY is not set"
    ):
        build_runtime_resources(llm_service=None, yf_fetcher=object())


def test_openrouter_fallback_models_parse_comma_list(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_FALLBACK_MODELS", " a/b, ,c/d ")

    assert settings.openrouter_fallback_models == ["a/b", "c/d"]
    assert settings.OPENROUTER_MODEL == "openai/gpt-6.2-sol"
