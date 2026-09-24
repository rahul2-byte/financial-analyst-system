"""Create and validate immutable permitted-source snapshot artifacts."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_CANDIDATE_SOURCE_FIELDS = (
    "source_id",
    "source_url",
    "publisher",
    "retrieved_at",
    "permitted_use",
    "sha256",
)


def freeze_snapshot(
    root: Path,
    *,
    snapshot_id: str,
    source_url: str,
    publisher: str,
    content: bytes,
    content_type: str,
    permitted_use: str,
    retrieved_at: datetime | None = None,
) -> dict[str, Any]:
    """Write one content-addressed snapshot and return its manifest record."""
    if not snapshot_id or not source_url or not publisher or not permitted_use:
        raise ValueError(
            "snapshot identity, source, publisher, and permitted use are required"
        )
    timestamp = retrieved_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("retrieved_at must include a timezone")
    digest = hashlib.sha256(content).hexdigest()
    relative_path = Path("snapshots") / f"{snapshot_id}.bin"
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != content:
        raise ValueError("snapshot id already contains different content")
    target.write_bytes(content)
    return {
        "id": snapshot_id,
        "url": source_url,
        "publisher": publisher,
        "content_type": content_type,
        "permitted_use": permitted_use,
        "retrieved_at": timestamp.astimezone(UTC).isoformat(),
        "sha256": digest,
        "path": relative_path.as_posix(),
    }


def validate_snapshot_record(root: Path, record: dict[str, Any]) -> list[str]:
    """Return integrity errors for one snapshot record and its stored bytes."""
    errors: list[str] = []
    for field in (
        "id",
        "url",
        "publisher",
        "content_type",
        "permitted_use",
        "retrieved_at",
        "sha256",
        "path",
    ):
        if not record.get(field):
            errors.append(f"snapshot missing {field}")
    path = root / str(record.get("path", ""))
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        errors.append("snapshot path escapes root")
        return errors
    if not path.is_file():
        errors.append("snapshot file is missing")
    elif hashlib.sha256(path.read_bytes()).hexdigest() != record.get("sha256"):
        errors.append("snapshot hash mismatch")
    try:
        datetime.fromisoformat(str(record.get("retrieved_at")))
    except ValueError:
        errors.append("snapshot timestamp is invalid")
    return errors


def validate_candidate_source_record(record: dict[str, Any]) -> list[str]:
    """Reject candidate records that pretend to contain frozen source metadata."""
    errors: list[str] = []
    if record.get("status") != "pending_owner_source":
        errors.append("candidate source must remain unresolved")
    for field in _CANDIDATE_SOURCE_FIELDS:
        if field not in record:
            errors.append(f"candidate source requires {field}")
    if any(record.get(field) not in (None, "") for field in _CANDIDATE_SOURCE_FIELDS):
        errors.append("candidate source must remain unresolved")
    return errors
