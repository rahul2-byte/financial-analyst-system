from pathlib import Path

import pytest
from finai.cli import _validate_cli_paths


def test_cli_rejects_broad_data_directory() -> None:
    with pytest.raises(ValueError):
        _validate_cli_paths(Path.home(), None)


def test_cli_rejects_missing_replay_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _validate_cli_paths(tmp_path / "data", tmp_path / "missing.json")
