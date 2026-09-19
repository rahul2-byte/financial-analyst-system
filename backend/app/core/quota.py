"""Small SQLite-backed provider request budget shared by app and CLI."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class QuotaExceeded(RuntimeError):
    """The local provider budget is exhausted."""


class RequestQuota:
    def __init__(self, path: Path, *, per_second: int = 2) -> None:
        self.path = path
        self.per_second = per_second
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS requests (provider TEXT NOT NULL, occurred REAL NOT NULL)"
            )
            connection.commit()

    def reserve(self, provider: str) -> None:
        now = time.time()
        with sqlite3.connect(self.path, timeout=5) as connection:
            connection.execute("DELETE FROM requests WHERE occurred < ?", (now - 1.0,))
            count = connection.execute(
                "SELECT COUNT(*) FROM requests WHERE provider = ?", (provider,)
            ).fetchone()[0]
            if count >= self.per_second:
                raise QuotaExceeded(f"{provider} request budget exhausted")
            connection.execute(
                "INSERT INTO requests(provider, occurred) VALUES (?, ?)",
                (provider, now),
            )
            connection.commit()
