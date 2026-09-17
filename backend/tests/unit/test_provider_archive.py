from datetime import UTC, datetime

import pytest
from app.observability.provider_archive import (
    ProviderArchive,
    ProviderArchiveError,
    ProviderSnapshot,
)


def test_archive_round_trip_preserves_raw_payload_and_content_hash(tmp_path) -> None:
    archive = ProviderArchive(tmp_path)
    snapshot = ProviderSnapshot(
        provider="fixture",
        operation="prices",
        payload={"close": 123.4},
        fetched_at=datetime(2026, 9, 18, tzinfo=UTC),
    )

    stored = archive.store(snapshot)
    loaded = archive.load(stored.content_hash)

    assert loaded.payload == {"close": 123.4}
    assert loaded.content_hash == stored.content_hash
    assert stored.content_hash in str(archive.path_for(stored.content_hash))


def test_archive_rejects_corrupted_snapshot(tmp_path) -> None:
    archive = ProviderArchive(tmp_path)
    stored = archive.store(
        ProviderSnapshot(
            provider="fixture",
            operation="prices",
            payload={"close": 123.4},
            fetched_at=datetime(2026, 9, 18, tzinfo=UTC),
        )
    )
    archive.path_for(stored.content_hash).write_text("{}", encoding="utf-8")

    with pytest.raises(ProviderArchiveError, match="content hash"):
        archive.load(stored.content_hash)
