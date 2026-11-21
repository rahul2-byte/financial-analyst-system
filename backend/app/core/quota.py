"""Small SQLite-backed provider request budget shared by app and CLI.

``reserve`` is the synchronous fail-fast check (raises ``QuotaExceeded``).
``acquire`` is the async, rate-limit-aware variant: when only the per-second
limit is saturated it waits for the next free slot instead of failing, so any
number of concurrent callers share the configured rate without tripping it.
Minute and 30-minute budgets are never waited on; they still fail closed.
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
import threading
import time
import weakref
from pathlib import Path


class QuotaExceeded(RuntimeError):
    """The local provider budget is exhausted."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        # Seconds until a per-second slot frees up; None when waiting is pointless.
        self.retry_after = retry_after


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
        # One connection per quota object (per process), serialised by a lock.
        self._lock = threading.Lock()
        self._connection: sqlite3.Connection | None = None
        # asyncio locks are loop-bound; keep one per running loop.
        self._async_locks: weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop, asyncio.Lock
        ] = weakref.WeakKeyDictionary()
        with self._lock:
            self._connect()

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            # Autocommit mode; transactions are explicit (BEGIN IMMEDIATE) so
            # count-then-insert is atomic across processes.
            connection = sqlite3.connect(
                self.path, timeout=5, isolation_level=None, check_same_thread=False
            )
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA synchronous=NORMAL")
            except sqlite3.DatabaseError:
                pass  # keep the default journal if WAL is unsupported here
            connection.execute(
                "CREATE TABLE IF NOT EXISTS requests (provider TEXT NOT NULL, occurred REAL NOT NULL)"
            )
            self._connection = connection
        return self._connection

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def __del__(self) -> None:
        with contextlib.suppress(Exception):  # interpreter shutdown
            self.close()

    def reserve(self, provider: str) -> None:
        with self._lock:
            connection = self._connect()
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._reserve(connection, provider)
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            connection.execute("COMMIT")

    def _reserve(self, connection: sqlite3.Connection, provider: str) -> None:
        now = time.time()
        oldest_window = 30 * 60 if self.per_30_minutes else 60
        connection.execute(
            "DELETE FROM requests WHERE occurred < ?", (now - oldest_window,)
        )
        recent = [
            row[0]
            for row in connection.execute(
                "SELECT occurred FROM requests "
                "WHERE provider = ? AND occurred >= ? ORDER BY occurred",
                (provider, now - 1),
            )
        ]
        if len(recent) >= self.per_second:
            # The slot frees when the (len - per_second + 1)-th oldest ages out.
            frees_at = recent[len(recent) - self.per_second] + 1
            raise QuotaExceeded(
                f"{provider} request budget exhausted",
                retry_after=max(0.0, frees_at - now),
            )
        if self.per_minute is not None:
            minute_count = connection.execute(
                "SELECT COUNT(*) FROM requests WHERE provider = ? AND occurred >= ?",
                (provider, now - 60),
            ).fetchone()[0]
            if minute_count >= self.per_minute:
                raise QuotaExceeded(f"{provider} minute request budget exhausted")
        if self.per_30_minutes is not None:
            half_hour_count = connection.execute(
                "SELECT COUNT(*) FROM requests WHERE provider = ? AND occurred >= ?",
                (provider, now - 30 * 60),
            ).fetchone()[0]
            if half_hour_count >= self.per_30_minutes:
                raise QuotaExceeded(f"{provider} 30-minute request budget exhausted")
        connection.execute(
            "INSERT INTO requests(provider, occurred) VALUES (?, ?)",
            (provider, now),
        )

    async def acquire(self, provider: str) -> None:
        """Reserve a slot, waiting (not failing) while only the per-second cap binds."""
        loop = asyncio.get_running_loop()
        lock = self._async_locks.get(loop)
        if lock is None:
            lock = self._async_locks[loop] = asyncio.Lock()
        # The async lock keeps waiters in FIFO order so none is starved.
        async with lock:
            while True:
                try:
                    self.reserve(provider)
                    return
                except QuotaExceeded as exc:
                    if exc.retry_after is None:
                        raise
                    await asyncio.sleep(exc.retry_after + 0.005)
