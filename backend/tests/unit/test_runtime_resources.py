from datetime import UTC, datetime

from app.config import settings
from app.core.resources import build_runtime_resources
from app.observability.provider_archive import ProviderArchive, ProviderSnapshot
from app.services.chatgpt_codex_service import ChatGPTCodexService
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
            provider="hive",
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


def test_resource_builder_uses_chatgpt_as_primary_only_when_enabled(
    monkeypatch,
):
    monkeypatch.setattr(settings, "FINAI_CHATGPT_CODEX_ENABLED", True)
    monkeypatch.setattr(settings, "FINAI_CHATGPT_CODEX_PRIMARY", True)

    resources = build_runtime_resources(llm_service=None, yf_fetcher=object())

    assert isinstance(resources.llm_service, ChatGPTCodexService)
    assert resources.llm_service.fallback.provider_name == "hive"


def test_chatgpt_model_tiers_are_configured(monkeypatch):
    monkeypatch.setattr(settings, "FINAI_CHATGPT_CODEX_ENABLED", True)
    monkeypatch.setattr(settings, "FINAI_CHATGPT_CODEX_PRIMARY", True)
    monkeypatch.setattr(settings, "FINAI_CHATGPT_CODEX_LUNA_MODEL", "luna-test")
    monkeypatch.setattr(settings, "FINAI_CHATGPT_CODEX_TERRA_MODEL", "terra-test")
    monkeypatch.setattr(settings, "FINAI_CHATGPT_CODEX_SOL_MODEL", "sol-test")
    monkeypatch.setattr(settings, "FINAI_CHATGPT_CODEX_ASTRA_MODEL", "astra-test")

    assert settings.FINAI_CHATGPT_CODEX_LUNA_MODEL == "luna-test"
    assert settings.FINAI_CHATGPT_CODEX_TERRA_MODEL == "terra-test"
    assert settings.FINAI_CHATGPT_CODEX_SOL_MODEL == "sol-test"
    assert settings.FINAI_CHATGPT_CODEX_ASTRA_MODEL == "astra-test"
