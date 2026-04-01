from __future__ import annotations

from pathlib import Path


def get_backend_root() -> Path:
    """Return absolute backend root path."""

    return Path(__file__).parent.parent.parent.resolve()


def resolve_backend_path(relative_path: str) -> Path:
    """Resolve a backend-relative path."""

    return (get_backend_root() / relative_path).resolve()
