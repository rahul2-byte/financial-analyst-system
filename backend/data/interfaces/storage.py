from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from data.schemas.market import OHLCVData
from data.schemas.text import ProcessedChunk


class IStructuredStorage(ABC):
    @abstractmethod
    def save_ohlcv(self, data: List[OHLCVData]) -> None:
        """Save a batch of OHLCV data."""
        pass

    @abstractmethod
    def get_ohlcv(
        self, ticker: str, start_date: datetime, end_date: datetime
    ) -> List[OHLCVData]:
        """Retrieve OHLCV data for a specific range."""
        pass

    @abstractmethod
    def get_latest_date(self, ticker: str) -> Optional[datetime]:
        """Get the most recent date available for a ticker."""
        pass

    @abstractmethod
    def get_earliest_date(self, ticker: str) -> Optional[datetime]:
        """Get the earliest date available for a ticker."""
        pass


class IVectorStorage(ABC):
    @abstractmethod
    def upsert_chunks(self, chunks: List[ProcessedChunk]) -> None:
        """Insert or update text chunks with embeddings."""
        pass

    @abstractmethod
    def chunk_and_upsert(self, text: str, metadata: dict) -> List[ProcessedChunk]:
        """Convenience method to chunk, embed, and upsert text."""
        pass

    @abstractmethod
    def search(
        self,
        query_embedding: List[float],
        limit: int = 5,
        query_text: Optional[str] = None,
        ticker: Optional[str] = None,
    ) -> List[ProcessedChunk]:
        """Search for relevant chunks using vector similarity or hybrid approach."""
        pass

    @abstractmethod
    def get_news_info(self, ticker: str) -> dict:
        """Get summary info of news coverage for a ticker."""
        pass
