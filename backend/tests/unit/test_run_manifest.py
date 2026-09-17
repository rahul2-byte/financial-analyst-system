from pathlib import Path
from uuid import uuid4

from app.observability.run_manifest import (
    RunManifest,
    load_run_manifest,
    save_run_manifest,
)


def test_run_manifest_round_trip(tmp_path: Path) -> None:
    manifest = RunManifest(
        run_id=uuid4(), query="analyze ABC", data_versions=("prices-v1",)
    )
    save_run_manifest(tmp_path, manifest)

    loaded = load_run_manifest(tmp_path, manifest.run_id)

    assert loaded == manifest
