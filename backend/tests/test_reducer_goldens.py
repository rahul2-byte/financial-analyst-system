"""Golden parity tests: committed TS reducer goldens must match the generator."""

from __future__ import annotations

from pathlib import Path

from scripts.gen_reducer_goldens import (
    GOLDENS_DIR,
    REPORTS_DIR,
    write_golden,
    write_report_fixtures,
)


def test_goldens_are_fresh(tmp_path: Path) -> None:
    generated = write_golden(tmp_path)
    assert generated, "generator wrote no files"
    for path in generated:
        committed = GOLDENS_DIR / path.name
        assert committed.exists(), f"missing committed golden {committed}"
        assert path.read_bytes() == committed.read_bytes(), (
            f"{committed} is stale; regenerate with "
            "PYTHONPATH=.:backend uv run --offline python scripts/gen_reducer_goldens.py"
        )


def test_report_fixtures_are_fresh(tmp_path: Path) -> None:
    generated = write_report_fixtures(tmp_path)
    assert len(generated) == 3
    for path in generated:
        committed = REPORTS_DIR / path.name
        assert committed.exists(), f"missing committed report fixture {committed}"
        assert path.read_bytes() == committed.read_bytes(), (
            f"{committed} is stale; regenerate with "
            "PYTHONPATH=.:backend uv run --offline python scripts/gen_reducer_goldens.py"
        )
