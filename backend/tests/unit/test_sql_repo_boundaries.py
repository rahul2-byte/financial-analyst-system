from contextlib import contextmanager
from unittest.mock import MagicMock

from storage.sql.health_repo import HealthRepository
from storage.sql.market_repo import MarketRepository


def test_health_repository_check_db_status_uses_is_db_up() -> None:
    repo = HealthRepository(session_provider=lambda: None)
    repo.is_db_up = MagicMock(return_value=True)

    result = repo.check_db_status()

    assert result == {"db_up": True, "status": "online"}


def test_market_repository_save_ohlcv_uses_single_execute_without_prefetch() -> None:
    mock_session = MagicMock()

    @contextmanager
    def session_provider():
        yield mock_session

    repo = MarketRepository(session_provider=session_provider)

    from data.schemas.market import OHLCVData

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

    repo.save_ohlcv(rows)

    assert mock_session.exec.call_count == 0
    assert mock_session.execute.call_count == 1
