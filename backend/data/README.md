# Data Pipeline

This module handles the fetching, processing, and storage of financial data.

## Architecture

- **Interfaces**: Defined in `backend/data/interfaces/`. Decouple fetching and storage.
- **Providers**: `YFinanceFetcher` is the current implementation for OHLCV and News.
- **Storage**:
  - **Structured**: Postgres (via SQLAlchemy/SQLModel). Stores OHLCV.
  - **Vector**: Qdrant. Stores News/Text chunks.
- **Orchestrator**: `DataPipeline` in `backend/data/pipeline.py`. Handles synchronization, batching, and gap analysis.

## Setup

1. Ensure Docker is running:
   ```bash
   docker-compose up -d
   ```

2. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```

3. Run Verification:
   ```bash
   python verify_pipeline.py
   ```

## Configuration

Edit `backend/config/settings.py` or `.env` to configure database URLs and API keys.
