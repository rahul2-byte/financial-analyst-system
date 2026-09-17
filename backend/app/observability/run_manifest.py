from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RunManifest(BaseModel):
    """Minimal reproducibility record for one AgentLoop run."""

    model_config = ConfigDict(frozen=True)

    run_id: UUID
    query: str = Field(min_length=1)
    model_id: str | None = None
    prompt_version: str | None = None
    data_versions: tuple[str, ...] = ()
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    terminal_status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def save_run_manifest(root: Path, manifest: RunManifest) -> Path:
    """Write a run manifest atomically enough for local artifact storage."""
    target = root / "runs" / str(manifest.run_id) / "manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def load_run_manifest(root: Path, run_id: UUID) -> RunManifest:
    """Load and validate a persisted run manifest."""
    path = root / "runs" / str(run_id) / "manifest.json"
    return RunManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
