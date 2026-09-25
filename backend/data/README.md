# Data layer

The data layer fetches, validates, normalizes, and returns current-run evidence to `FinancialToolRunner`. It does not own a persistent corpus or a graph database.

## Providers

- `data/providers/yfinance.py:YFinanceFetcher` supplies OHLCV, fundamentals, statements, macro indicators, and provider news. Price responses include quality checks and provenance.
- `data/providers/upstox.py:UpstoxFetcher` is optional. When configured, it supports NSE instrument resolution, candles, fundamentals, news, market status/holidays, and market context. Requests are quota-limited through the local SQLite quota store.
- `data/news_pipeline/` combines TinyFish and optional Upstox search, article extraction, URL normalization, deduplication, relevance checks, and source-quality scoring.

## Runtime boundary

`backend/app/core/resources.py:build_runtime_resources()` constructs providers. `backend/app/core/agent_loop/tool_runner.py:FinancialToolRunner` calls them, attaches or preserves provenance, invokes deterministic quant analysis, and supplies normalized results to `AgentLoop` evidence accounting. Completed provider payloads may be stored in the content-addressed `.finai/provider-snapshots/` archive.

Replay adapters in `data/news_pipeline/replay.py` and `data/providers/yfinance.py:ReplayYFinanceFetcher` replace live dependencies when `--replay-snapshots` is supplied. Missing or hash-mismatched snapshots fail rather than silently fetching live data.

Run local checks from the repository root:

```bash
uv sync
uv run python -m compileall -q backend
uv run ruff check backend
```
