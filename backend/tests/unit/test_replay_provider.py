import asyncio
from datetime import UTC, datetime

import pytest
from app.core.agent_loop.replay import ReplayModelStream
from app.observability.provider_archive import ProviderArchive, ProviderSnapshot
from data.providers.yfinance import ReplayYFinanceFetcher


def test_replay_fetcher_returns_archived_payload_without_a_live_provider(
    tmp_path,
) -> None:
    archive = ProviderArchive(tmp_path)
    snapshot = archive.store(
        ProviderSnapshot(
            provider="yfinance",
            operation="fetch_stock_price",
            payload={"ticker": "ABC.NS", "data": [{"Close": 12.0}]},
            fetched_at=datetime(2026, 9, 18, tzinfo=UTC),
        )
    )
    fetcher = ReplayYFinanceFetcher(
        archive, {"fetch_stock_price": snapshot.content_hash}
    )

    result = fetcher.fetch_stock_price("ABC", "1y", "1d")

    assert result == {"ticker": "ABC.NS", "data": [{"Close": 12.0}]}


def test_replay_fetcher_never_falls_back_when_snapshot_is_missing(tmp_path) -> None:
    fetcher = ReplayYFinanceFetcher(ProviderArchive(tmp_path), {})

    with pytest.raises(RuntimeError, match="replay snapshot"):
        fetcher.fetch_company_fundamentals("ABC")


def test_replay_model_stream_consumes_ordered_snapshots(tmp_path) -> None:
    archive = ProviderArchive(tmp_path)
    first = archive.store(
        ProviderSnapshot(
            provider="hive",
            operation="model_stream",
            payload=[{"event": "token", "data": "first"}],
            fetched_at=datetime(2026, 9, 18, tzinfo=UTC),
        )
    )
    second = archive.store(
        ProviderSnapshot(
            provider="hive",
            operation="model_stream",
            payload=[{"event": "token", "data": "second"}],
            fetched_at=datetime(2026, 9, 18, tzinfo=UTC),
        )
    )
    stream = ReplayModelStream(archive, [first.content_hash, second.content_hash])

    async def collect() -> list[dict]:
        return [event async for event in stream.generate_stream([], "model")]

    assert asyncio.run(collect()) == [{"event": "token", "data": "first"}]
    assert asyncio.run(collect()) == [{"event": "token", "data": "second"}]
    with pytest.raises(RuntimeError, match="replay model stream exhausted"):
        stream.generate_stream([], "model")
