from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from sqlmodel import text


class AdminRepository:
    def __init__(self, session_provider: Callable[[], AbstractContextManager[Any]]):
        self._session_provider = session_provider

    def get_table_count(self) -> int:
        with self._session_provider() as session:
            statement = text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"
            )
            result = session.execute(statement).first()
            return result[0] if result else 0

    def get_table_names(self) -> list[str]:
        with self._session_provider() as session:
            statement = text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';"
            )
            results = session.execute(statement).fetchall()
            return [row[0] for row in results] if results else []

    def get_column_names(self, table_name: str) -> list[str]:
        with self._session_provider() as session:
            statement = text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = :table_name;"
            )
            results = session.execute(statement, {"table_name": table_name}).fetchall()
            return [row[0] for row in results] if results else []

    def get_db_size(self) -> str:
        with self._session_provider() as session:
            statement = text("SELECT pg_size_pretty(pg_database_size(current_database()));")
            result = session.execute(statement).first()
            return result[0] if result else "0 bytes"
