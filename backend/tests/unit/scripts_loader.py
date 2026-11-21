"""Load backend/scripts/perf_report.py (scripts is not a package)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_perf_report() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "perf_report.py"
    spec = importlib.util.spec_from_file_location("perf_report", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
