from contextlib import contextmanager
from unittest.mock import MagicMock

from data.schemas.market import OHLCVData
from storage.sql.client import PostgresClient


def test_save_ohlcv_avoids_prefetching_existing_dates_before_insert():
    client = PostgresClient.__new__(PostgresClient)
    mock_session = MagicMock()

    @contextmanager
    def fake_session():
        yield mock_session

    client.get_session = fake_session  # type: ignore[method-assign]

    rows = [
        OHLCVData(
            ticker="AAPL",
            date="2025-01-02",
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0,
            volume=1000,
            adjusted_close=103.0,
        )
    ]

    client.save_ohlcv(rows)

    assert mock_session.exec.call_count == 0
    assert mock_session.execute.call_count == 1
