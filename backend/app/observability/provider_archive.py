"""Immutable local snapshots of provider payloads for audit and replay."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProviderArchiveError(RuntimeError):
    """A snapshot is missing, malformed, or does not match its hash."""


class ProviderSnapshot(BaseModel):
    """The exact provider payload and context needed to replay it."""

    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    payload: Any
    fetched_at: datetime
    content_hash: str | None = None

    def with_hash(self) -> ProviderSnapshot:
        return self.model_copy(update={"content_hash": _content_hash(self)})


class ProviderArchive:
    """Filesystem archive keyed by canonical snapshot content."""

    def __init__(self, root: Path) -> None:
        self.root = root / "provider-snapshots"

    def store(self, snapshot: ProviderSnapshot) -> ProviderSnapshot:
        stored = snapshot.with_hash()
        target = self.path_for(stored.content_hash or "")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            temporary = target.with_suffix(".tmp")
            temporary.write_text(
                stored.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
            temporary.replace(target)
        return stored

    def load(self, content_hash: str) -> ProviderSnapshot:
        target = self.path_for(content_hash)
        try:
            snapshot = ProviderSnapshot.model_validate_json(
                target.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            message = (
                f"snapshot content hash mismatch: {content_hash}"
                if target.exists()
                else f"snapshot unavailable: {content_hash}"
            )
            raise ProviderArchiveError(message) from exc
        if (
            snapshot.content_hash != content_hash
            or _content_hash(snapshot) != content_hash
        ):
            raise ProviderArchiveError(
                f"snapshot content hash mismatch: {content_hash}"
            )
        return snapshot

    def path_for(self, content_hash: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
            raise ProviderArchiveError("invalid snapshot content hash")
        return self.root / content_hash[:2] / f"{content_hash}.json"


def _content_hash(snapshot: ProviderSnapshot) -> str:
    payload = snapshot.model_dump(mode="json", exclude={"content_hash"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
