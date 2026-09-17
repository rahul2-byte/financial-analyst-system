from datetime import UTC, datetime

from evals.snapshots import freeze_snapshot, validate_snapshot_record


def test_snapshot_manifest_contains_timestamp_and_matching_hash(tmp_path) -> None:
    record = freeze_snapshot(
        tmp_path,
        snapshot_id="source-1",
        source_url="https://example.test/source",
        publisher="Example",
        content=b"permitted public excerpt",
        content_type="text/plain",
        permitted_use="local evaluation",
        retrieved_at=datetime(2026, 9, 18, tzinfo=UTC),
    )

    assert validate_snapshot_record(tmp_path, record) == []
    assert record["sha256"]
    assert record["retrieved_at"].endswith("+00:00")


def test_snapshot_validation_detects_tampering(tmp_path) -> None:
    record = freeze_snapshot(
        tmp_path,
        snapshot_id="source-1",
        source_url="https://example.test/source",
        publisher="Example",
        content=b"original",
        content_type="text/plain",
        permitted_use="local evaluation",
    )
    (tmp_path / record["path"]).write_bytes(b"changed")

    assert "snapshot hash mismatch" in validate_snapshot_record(tmp_path, record)
