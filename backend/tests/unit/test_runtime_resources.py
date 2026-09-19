from datetime import UTC, datetime

from app.config import settings
from app.core.resources import build_runtime_resources
from app.observability.provider_archive import ProviderArchive, ProviderSnapshot
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
