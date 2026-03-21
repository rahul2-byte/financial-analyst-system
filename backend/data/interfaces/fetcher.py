from abc import ABC, abstractmethod
from typing import List
from datetime import datetime
from data.schemas.market import OHLCVData
from data.schemas.text import NewsArticle


class IDataFetcher(ABC):
    @abstractmethod
    def fetch_ohlcv(
        self, ticker: str, start_date: datetime, end_date: datetime
    ) -> List[OHLCVData]:
        """Fetch historical OHLCV data for a given ticker and date range."""
        pass

    @abstractmethod
    def fetch_news(self, ticker: str, limit: int = 10) -> List[NewsArticle]:
        """Fetch latest news articles for a given ticker."""
        pass
