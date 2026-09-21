"""Small SQLite-backed provider request budget shared by app and CLI."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class QuotaExceeded(RuntimeError):
    """The local provider budget is exhausted."""


class RequestQuota:
    def __init__(
        self,
        path: Path,
        *,
        per_second: int = 2,
        per_minute: int | None = None,
        per_30_minutes: int | None = None,
    ) -> None:
        self.path = path
        self.per_second = per_second
        self.per_minute = per_minute
        self.per_30_minutes = per_30_minutes
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS requests (provider TEXT NOT NULL, occurred REAL NOT NULL)"
            )
            connection.commit()

    def reserve(self, provider: str) -> None:
        now = time.time()
        with sqlite3.connect(self.path, timeout=5) as connection:
            oldest_window = 30 * 60 if self.per_30_minutes else 60
            connection.execute(
                "DELETE FROM requests WHERE occurred < ?", (now - oldest_window,)
            )
            count = connection.execute(
                "SELECT COUNT(*) FROM requests WHERE provider = ? AND occurred >= ?",
                (provider, now - 1),
            ).fetchone()[0]
            if count >= self.per_second:
                raise QuotaExceeded(f"{provider} request budget exhausted")
            if self.per_minute is not None:
                minute_count = connection.execute(
                    "SELECT COUNT(*) FROM requests "
                    "WHERE provider = ? AND occurred >= ?",
                    (provider, now - 60),
                ).fetchone()[0]
                if minute_count >= self.per_minute:
                    raise QuotaExceeded(f"{provider} minute request budget exhausted")
            if self.per_30_minutes is not None:
                half_hour_count = connection.execute(
                    "SELECT COUNT(*) FROM requests "
                    "WHERE provider = ? AND occurred >= ?",
                    (provider, now - 30 * 60),
                ).fetchone()[0]
                if half_hour_count >= self.per_30_minutes:
                    raise QuotaExceeded(
                        f"{provider} 30-minute request budget exhausted"
                    )
            connection.execute(
                "INSERT INTO requests(provider, occurred) VALUES (?, ?)",
                (provider, now),
            )
            connection.commit()
