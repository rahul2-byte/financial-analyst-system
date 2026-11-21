"""Startup-cost guards: heavy modules must stay out of the bridge import path."""

import ast
import subprocess
import sys

_HEAVY = ("pandas_ta_classic", "numba", "pandas", "app.core.agent_loop")


def _loaded(module: str) -> list[str]:
    code = (
        "import sys, importlib\n"
        f"importlib.import_module({module!r})\n"
        f"print([m for m in {_HEAVY!r} if m in sys.modules])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    return ast.literal_eval(result.stdout.strip())


def test_bridge_server_import_does_not_load_heavy_modules() -> None:
    assert _loaded("finai.bridge.server") == []


def test_cli_import_does_not_load_heavy_modules() -> None:
    assert _loaded("finai.cli") == []
