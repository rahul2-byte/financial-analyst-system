"""Run FIN-AI with ``python -m finai``."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .session import FinAIRepl

__all__ = ["FinAIRepl", "main"]


def main() -> None:
    """Load the CLI lazily so missing environment dependencies are actionable."""
    try:
        from .cli import main as cli_main
    except ModuleNotFoundError as exc:
        if exc.name in {"pydantic", "textual", "httpx", "fastapi"}:
            print(
                "FIN-AI dependencies are missing from this Python environment.\n"
                "Run with the project environment: uv run python -m finai --help\n"
                "or activate .venv before running python -m finai.",
                file=sys.stderr,
            )
            raise SystemExit(2) from exc
        raise
    cli_main()


def __getattr__(name: str):
    if name == "FinAIRepl":
        from .session import FinAIRepl

        return FinAIRepl
    raise AttributeError(name)

if __name__ == "__main__":
    main()
