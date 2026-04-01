from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import text

from data.schemas.market import OHLCVData
from storage.sql.models import OHLCV


class MarketRepository:
    def __init__(self, session_provider: Callable[[], AbstractContextManager[Any]]):
        self._session_provider = session_provider

    def save_ohlcv(self, data: list[OHLCVData]) -> None:
        if not data:
            return

        with self._session_provider() as session:
            rows = [
                {
                    "ticker": item.ticker,
                    "date": item.date,
                    "open": item.open,
                    "high": item.high,
                    "low": item.low,
                    "close": item.close,
                    "volume": item.volume,
                    "adjusted_close": item.adjusted_close,
                }
                for item in data
            ]

            stmt = pg_insert(OHLCV).values(rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["ticker", "date"])
            session.execute(stmt)

    def has_any_data(self) -> bool:
        with self._session_provider() as session:
            result = session.execute(text("SELECT 1 FROM ohlcv_data LIMIT 1")).first()
            return result is not None
