from datetime import datetime, timedelta
import logging
from config import settings
from data.interfaces.fetcher import IDataFetcher
from data.interfaces.storage import IStructuredStorage, IVectorStorage
from data.processors.text import TextProcessor

logger = logging.getLogger(__name__)


class DataPipeline:
    def __init__(
        self,
        fetcher: IDataFetcher,
        structured_storage: IStructuredStorage,
        vector_storage: IVectorStorage,
        text_processor: TextProcessor,
    ):
        self.fetcher = fetcher
        self.structured_storage = structured_storage
        self.vector_storage = vector_storage
        self.text_processor = text_processor

    def sync_market_data(self, ticker: str) -> None:
        """
        Synchronizes market data for a ticker.
        Checks DB, fetches missing data in batches, and updates DB.
        """
        logger.info(f"Starting sync for {ticker}")

        # 1. Check existing data coverage
        latest_date = self.structured_storage.get_latest_date(ticker)
        today = datetime.now()

        start_date = today - timedelta(days=365 * settings.BATCH_SIZE_YEARS)

        if latest_date:
            # If we have data, start from the next day
            start_date = latest_date + timedelta(days=1)
            logger.info(
                f"Found existing data up to {latest_date}. Fetching from {start_date}"
            )
        else:
            logger.info(f"No existing data. Fetching full history from {start_date}")

        if start_date >= today:
            logger.info("Data is up to date.")
            return

        # 2. Batch Fetching Logic
        current_start = start_date
        while current_start < today:
            # Define batch end (e.g., 1 year chunks or full range)
            # YFinance handles large ranges well, but for robustness we can batch
            # Let's fetch the remaining range in one go for simplicity if YFinance supports it,
            # or break it if needed. Here we assume the fetcher handles the range.
            # But the requirement asked for 5 year chunks.

            batch_end = min(current_start + timedelta(days=365 * 5), today)

            logger.info(f"Fetching batch: {current_start.date()} -> {batch_end.date()}")

            try:
                data = self.fetcher.fetch_ohlcv(ticker, current_start, batch_end)
                if data:
                    self.structured_storage.save_ohlcv(data)
                    logger.info(f"Saved {len(data)} records.")
                else:
                    logger.warning(
                        f"No data returned for batch {current_start} -> {batch_end}"
                    )
            except Exception as e:
                logger.error(f"Failed to fetch batch: {e}")
                # Depending on policy, we might break or continue
                # For now, we log and break to avoid infinite loops on error
                break

            current_start = batch_end + timedelta(days=1)

    def sync_news(self, ticker: str) -> None:
        """
        Fetches latest news, chunks it, and stores in vector DB.
        """
        logger.info(f"Syncing news for {ticker}")

        try:
            articles = self.fetcher.fetch_news(ticker)
            if not articles:
                logger.info("No news found.")
                return

            all_chunks = []
            for article in articles:
                # Validate/Clean content
                if not article.content:
                    continue

                chunks = self.text_processor.chunk_text(
                    text=article.content,
                    metadata={
                        "ticker": ticker,
                        "source": article.source,
                        "url": article.url,
                        "published_date": article.published_date.isoformat(),
                    },
                )

                # In a real system, we'd generate embeddings here using an Embedding Model
                # For now, we assume the Vector Storage or an intermediate step handles it
                # OR we mock the embedding if the storage requires it immediately.
                # QdrantStorage expects embeddings.

                # Mock embedding for now since we don't have an embedding model loaded
                # In production, call OpenAI/HuggingFace here.
                for chunk in chunks:
                    chunk.embedding = [0.1] * 1536  # Mock 1536-dim vector

                all_chunks.extend(chunks)

            if all_chunks:
                self.vector_storage.upsert_chunks(all_chunks)
                logger.info(f"Upserted {len(all_chunks)} news chunks.")

        except Exception as e:
            logger.error(f"Failed to sync news: {e}")
