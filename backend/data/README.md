# Data pipeline

The data layer fetches, validates, and normalizes current-run evidence.

- `data/providers/yfinance.py` supplies OHLCV, fundamentals, macro, and provider news.
- `data/news_pipeline/` searches with TinyFish and extracts article/PDF text.
- No database, vector index, embedding model, or scheduled persistence is required.
- Results are passed through graph state and captured in `.finai/` run artifacts.

Run from the repository root:

```bash
uv sync
uv run python -m compileall -q backend
uv run ruff check backend
```
