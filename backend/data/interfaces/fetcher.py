from abc import ABC, abstractmethod
from datetime import datetime

from data.schemas.market import OHLCVData
from data.schemas.text import NewsArticle


class IDataFetcher(ABC):
    @abstractmethod
    def fetch_ohlcv(
        self, ticker: str, start_date: datetime, end_date: datetime
    ) -> list[OHLCVData]:
        """Fetch historical OHLCV data for a given ticker and date range."""

    @abstractmethod
    def fetch_news(self, ticker: str, limit: int = 10) -> list[NewsArticle]:
        """Fetch latest news articles for a given ticker."""
