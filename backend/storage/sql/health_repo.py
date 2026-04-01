from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from sqlmodel import text


class HealthRepository:
    def __init__(self, session_provider: Callable[[], AbstractContextManager[Any]]):
        self._session_provider = session_provider

    def is_db_up(self) -> bool:
        try:
            with self._session_provider() as session:
                session.execute(text("SELECT 1")).first()
            return True
        except Exception:
            return False

    def check_db_status(self) -> dict[str, Any]:
        is_up = self.is_db_up()
        return {"db_up": is_up, "status": "online" if is_up else "offline"}
