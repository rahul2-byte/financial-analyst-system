import logging
import sys
import os

# Ensure backend is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.data.providers.yfinance import YFinanceFetcher
from backend.storage.sql.client import PostgresClient
from backend.storage.vector.client import QdrantStorage
from backend.data.processors.text import TextProcessor
from backend.data.pipeline import DataPipeline

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    try:
        logger.info("Initializing components...")

        # 1. Initialize Storage Clients
        # Note: Ensure Docker containers are running!
        pg_client = PostgresClient()
        qdrant_client = QdrantStorage()

        # 2. Initialize Fetcher & Processor
        fetcher = YFinanceFetcher()
        processor = TextProcessor()

        # 3. Initialize Pipeline
        pipeline = DataPipeline(
            fetcher=fetcher,
            structured_storage=pg_client,
            vector_storage=qdrant_client,
            text_processor=processor,
        )

        # 4. Test Market Data Sync
        ticker = "AAPL"
        logger.info(f"Testing market data sync for {ticker}...")
        pipeline.sync_market_data(ticker)

        # Verify data was stored
        latest = pg_client.get_latest_date(ticker)
        logger.info(f"Latest date in DB for {ticker}: {latest}")

        # 5. Test News Sync
        logger.info(f"Testing news sync for {ticker}...")
        pipeline.sync_news(ticker)

        # Verify vector search
        # Mock embedding for search query
        mock_query = [0.1] * 1536
        results = qdrant_client.search(mock_query)
        logger.info(f"Found {len(results)} news chunks via vector search.")

        logger.info("Verification complete!")

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
