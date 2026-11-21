# A2: Data and quant layer speed audit

Scope: backend/data, backend/quant, provider adapters in backend/app. No live network was used. Only synthetic micro-benchmarks (marked MEASURED); everything else is REASONED from code and config defaults.

## 1. Map of data calls per report

Typical full research turn (all paths go through `FinancialToolRunner`, backend/app/core/agent_loop/tool_runner.py):

| Step | Call | file:line | Notes |
|---|---|---|---|
| 0 | Instrument resolution (Upstox search, only if no explicit .NS ticker) | finai/session_runtime.py:327-352, app/core/instrument_resolution.py:160-185 | SYNC, runs on the event loop. 1 search + up to MAX_FALLBACK_SEARCHES sequential fallback searches |
| 1 | `data:fetch_stock_data` / `analysis:get_technical_overview` -> `_fetch_ohlcv` | tool_runner.py:973-990, :576, :700 | Upstox: resolve_instrument + fetch_candles, else `yf.download` via `fetch_stock_price` (yfinance.py:352) |
| 2 | `analysis:run_technical_scan` | tool_runner.py:640-690 | Calls `yf_fetcher.fetch_stock_price` directly, bypassing `_fetch_ohlcv` (no Upstox, no quality gate) |
| 3 | `analysis:run_fundamental_scan` | tool_runner.py:480-540 | `yf.Ticker.info` first (yfinance.py:522), then Upstox resolve + 8 sequential endpoints (upstox.py:155-175) |
| 4 | `data:fetch_fundamentals` | tool_runner.py:770-810 | Same as 3 but Upstox first |
| 5 | `news:fetch_news` | tool_runner.py:806-860 -> news_pipeline/runner.py:84 | Connectors in parallel (gather). TinyFish: up to 3 queries SEQUENTIAL (connectors.py:328), then up to 12 article extractions, 5 at a time (runner.py:122-130) |
| 6 | quant: `TechnicalEngine.analyze` in `asyncio.to_thread` (tool_runner.py:~600/~675), `FundamentalScanner` | quant/technical_engine.py:122 | MEASURED ~5-7 ms for 252 bars. Negligible |
| other | `fetch_financial_statements` (3 sequential property fetches, no retry/timeout, yfinance.py:~560), `fetch_macro_indicators` (5 sequential `Ticker.history`, yfinance.py:~620) | yfinance.py | Not on the default report path, but slow if invoked |

Existing caching: per-`FinancialToolRunner` TTL caches, OHLCV keyed (ticker, period, interval) 60 s intraday / 900 s daily, fundamentals 3600 s (tool_runner.py:247-316). Upstox `resolve_instrument` has a per-instance dict cache (upstox.py:47,97). The runtime also dedupes identical tool signatures in a run (runtime.py:1155). No disk cache; nothing is shared across CLI processes.

## 2. Ranked bottlenecks

### B1. Tool calls execute strictly one at a time (interaction point with orchestration audit)
- Where: backend/app/core/agent_loop/runtime.py:1081 (`for call in assistant.tool_calls:` ... `await tool_executor.execute`, :1231).
- Evidence: REASONED. When the model emits prices + fundamentals + news in one assistant message, they run back to back. Cost = sum, not max. Rough numbers: yf price 1-3 s, `Ticker.info` 1-4 s, news pipeline up to 45-60 s worst case (typically 8-25 s), so serial is ~15-35 s vs ~10-25 s concurrent.
- Impact: LARGEST single data-layer win, probably 30-50% of data wall-clock on multi-tool turns.
- Fix: execute independent read-only tools in the same assistant message with `asyncio.gather` (tools are already `async` and use `to_thread`), then append results in original call order so history and event ordering are unchanged. Keep news dependent on fundamentals' company name only as an optimisation (see B5).
- Risk: event ordering for the UI (emit start events up front, results in call order); the sqlite quota and the `turn_facts` / `last_technical_snapshot` shared mutable state on the runner needs a lock or ordered merge. Output values are unchanged.
- Owner note: this is in runtime.py, so coordinate with the orchestration auditor.

### B2. TinyFish news search queries are sequential, then extraction fans out
- Where: data/news_pipeline/connectors.py:328 (`for query_spec in queries`), default 3 queries (config TINYFISH_MAX_QUERIES_PER_RUN=3), per-query timeout 8 s, retry 1 with backoff 0.5 s, overall 45 s.
- Evidence: REASONED. 3 x ~1-3 s sequential; up to 3 x 8 s on slow responses.
- Impact: 2-6 s typical, up to ~16 s saved.
- Fix: `asyncio.gather` over the queries, keeping deterministic merge order (query order) so dedupe and `seen_result_keys` give identical output.
- RISK / CAUTION: `FINAI_PROVIDER_REQUESTS_PER_SECOND` defaults to 2 and `RequestQuota.reserve` (app/core/quota.py:29) raises `QuotaExceeded` rather than waiting, and `QuotaExceeded` is not retried. Firing 3 at once would trip the limit and turn into failures. Fix must stagger (semaphore of 2, or small sleep-until-slot in the client) or the limit must be raised after checking the TinyFish plan.
- Also: `TinyFishSearchClient` builds a fresh `httpx.AsyncClient` per request (tinyfish_client.py:~38), so every search pays a new TCP+TLS handshake (~100-300 ms each). Reuse one client per connector run.

### B3. Upstox fundamentals bundle: 8 sequential HTTP calls
- Where: data/providers/upstox.py:155-175 (`_fundamental_bundle`, plain for loop over 8 endpoints, each `httpx.get` with a new connection, timeout 20 s, retry 3).
- Evidence: REASONED. 8 x ~150-400 ms = 1.2-3.2 s; on failure each endpoint can burn 20 s x 3 attempts + backoff before degrading to a warning (worst case minutes).
- Impact: 1-3 s typical when Upstox is configured; large on outages.
- Fix: run the 8 endpoints through a `ThreadPoolExecutor(max_workers=4-8)` (Upstox limit is 50 req/s, so quota is fine) and use one `httpx.Client` for connection reuse. Merge results in the fixed endpoint order so the dict is identical.
- Risk: low. Keep the warnings list order stable. Use a shared client with `Client(timeout=...)` thread-safe.

### B4. Fundamentals path wastes the yfinance call when Upstox is configured, and blocks on a slow `.info`
- Where: tool_runner.py:497-515 (`run_fundamental_scan` always calls `yf_fetcher.fetch_company_fundamentals` first, then Upstox overrides the result on success); yfinance.py:522 (`.info` with 15 s timeout wrapped by `_call` with 3 attempts).
- Evidence: REASONED. `Ticker.info` is typically the slowest yfinance call (1-4 s, it fetches several Yahoo modules, plus crumb/cookie handshake on first use per process). Result is thrown away whenever Upstox returns an ISIN.
- Impact: 1-4 s on every fundamentals scan with Upstox on. Worst-case failure latency: timeout 15 s x 3 attempts + backoff (0.5/1 s) = ~46 s before `ProviderUnavailable`.
- Fix: (a) try Upstox first (as `data:fetch_fundamentals` already does at :770) and fall back to yfinance only on failure; (b) or launch both concurrently and prefer Upstox. (a) is simpler. Cut `YFINANCE_INFO_TIMEOUT_SECONDS` retry attempts for `.info` to 2 or make the timeout non-retried (timeouts are retried because `TimeoutError` is retryable, retry.py:40-47).
- Risk: medium-low. Output precedence must remain "Upstox wins when it has usable metrics". Note the two paths currently differ: scan path accepts any Upstox dict without the "usable metrics" check that :786 applies. Do not unify behaviour silently; keep each as is.

### B5. News tool waits on name lookup and runs after fundamentals
- Where: tool_runner.py:809-830. Company name comes from `_fundamentals_by_ticker` cache, else an extra sync Upstox `resolve_instrument` call. When the model calls news before fundamentals, one additional search round trip happens (cached after).
- Evidence: REASONED. Impact ~0.2-0.5 s, ordering dependent. Becomes a hard dependency if B1 is implemented (news reads fundamentals cache concurrently), so under gather the news tool may always miss the cache and do the Upstox lookup, or use the raw ticker as name.
- Fix: when parallelising, pre-resolve company name once per ticker with a small shared async lock/cache; or allow news to start with the Upstox short name and not depend on fundamentals.
- Risk: query text feeds news search, so the company name chosen can change which articles come back. Keep the same name precedence (fundamentals name > Upstox short_name > ticker) or news output changes.

### B6. Blocking sync Upstox instrument search on the event loop
- Where: finai/session_runtime.py:327-352 (`_resolve_instrument_context` is sync, called from the async turn at :104), -> `resolve_instrument` (instrument_resolution.py:160-185) -> `UpstoxFetcher.resolve_instrument` (upstox.py:95) -> `httpx.get` with timeout 20 s and 3 retries.
- Evidence: REASONED. The whole asyncio loop (spinner, bridge JSON-RPC, cancellation) is frozen during each search; the fallback loop does up to MAX_FALLBACK_SEARCHES more sequential searches when the first returns no candidates. Dict cache only helps repeated symbols; each phrase is a new key.
- Impact: perceived UI freeze of 0.3-2 s typical, and up to ~60 s on an outage (retry x timeout), with the frontend unresponsive (cancel is not serviced).
- Fix: wrap in `await asyncio.to_thread(...)` (call site is async-reachable) and run the fallback phrase searches in a small thread pool; short timeout (e.g. 5 s) for search specifically.
- Risk: low; resolution outputs unchanged. Keep result ordering so the "first exact hit" semantic is unchanged (iterate results in phrase order).

### B7. OHLCV cache gaps: key normalisation and path divergence
- Where: tool_runner.py:570, :661, :700 key = `(ticker, period, interval)` using the raw model-supplied string; `run_technical_scan` (:651-668) fetches via `yf_fetcher.fetch_stock_price` while `get_technical_overview` / `fetch_stock_data` use `_fetch_ohlcv` (Upstox first).
- Evidence: REASONED. "RELIANCE", "RELIANCE.NS", "reliance.ns" are three cache entries -> 3 downloads. Mixed use of overview and scan on the same ticker hits different providers but the same cache key, so the first caller decides the source (also a provenance-consistency concern).
- Impact: one redundant 1-3 s download per variant. Real in multi-tool turns where the model varies the spelling.
- Fix: normalise key with `parse_ticker(...).cache_key` (app/core/ticker.py:40 already exists) and route `run_technical_scan` through `_fetch_ohlcv`.
- Risk: routing the scan through `_fetch_ohlcv` could switch its source to Upstox (different provenance and values) when Upstox is configured, so treat that as a behaviour change and confirm with the owner. Key normalisation alone is safe.

### B8. yfinance fetches and conversion
- `fetch_stock_price` (yfinance.py:372-420): uses `period` given by the caller, default "1y" in tools, so history is not over-fetched by default. If the model passes "5y" or "max" it pulls it all, and technical engine needs ~200 bars for SMA200 only. REASONED, low impact.
- `fetch_ohlcv` (yfinance.py:282) uses `df.iterrows()` plus per-cell `_safe_get_value`, `_safe_get_date` (pd.Timestamp parse per row), and one pydantic model per row. REASONED: ~250 rows, roughly 10-40 ms. Only used on the legacy datetime-range path. Vectorise if it becomes hot. The `fetch_stock_price` path uses `to_dict(orient="records")` and a per-row `_localize` map (:394, ~250 `pd.Timestamp` constructions, MEASURED not done, est 5-15 ms). Negligible next to network.
- `yf.download` (single ticker) spins up its own thread pool and prints no progress; fine. It does not reuse a session between calls, so each call may re-handshake (crumb is cached by yfinance per process).
- `fetch_news` (yfinance.py:~655) and `fetch_financial_statements` have no timeout or retry; a hung socket blocks a worker thread indefinitely (the tool timeout at tool_execution.py:20 is 30 s default, news 120 s, which bounds it from above).
- `fetch_macro_indicators` makes 5 sequential `Ticker.history` calls: use `yf.download([...5 symbols], period="5d", group_by="ticker")` or threads. Impact 3-8 s if ever called; not on default path.

### B9. Retry/timeout settings that add failure latency
- retry.py `call_with_retry` + config (app/config/models.py:58-61): 3 attempts, 0.5 s base, 8 s cap, applied to every yfinance call. Timeout errors are retryable, so `.info` hanging at 15 s costs ~46 s. `yf.download` has no per-call timeout at all (yfinance.py:263/372), so a hang falls to the 30 s tool timeout.
- Upstox: timeout 20 s x 3 attempts per call (upstox.py:40, :74), and within the bundle x8 endpoints: worst case several minutes of serial failure (see B3).
- TinyFish: query timeout 8 s, 1 retry, total 45 s, pipeline total 60 s; extraction 8 s each in batches of 5 for up to 12 articles (3 waves, ~24 s worst case). News tool allowed 120 s.
- Fix: fail fast on repeated timeouts (do not retry TimeoutError for `.info`, cap Upstox read timeout to ~8-10 s for these small payloads), and add a simple circuit breaker (app/core/circuit_breaker.py exists for the LLM; reuse) so after the first provider outage the rest of the turn skips that provider.
- Risk: lower success rate on flaky networks; keep retries for 429/5xx.

### B10. News extraction: new thread pool and full-page fetch per article
- Where: news_pipeline/runner.py:41-55 (`_run_sync` creates a fresh `ThreadPoolExecutor(max_workers=1)` per article) and extractor.py:88-135 (trafilatura download + `_safe_get` with DNS/IP validation, 20 s stream timeout, up to 12 pages, semaphore 5).
- Evidence: REASONED. Thread creation is cheap (<1 ms); the real cost is fetching 12 pages, 5 concurrent, each up to 8 s timeout. Typical 3-10 s. `httpx.stream` per call, no connection reuse, no cross-turn article cache.
- Fix: raise semaphore to 8-12 (the cap is already 12 extractions), skip extraction when the search snippet is already long enough, and add an on-disk cache keyed by canonical URL (TTL hours) so repeat reports on the same ticker do not re-download. Cache the whole `last news result` per (ticker, window) for 10-15 min.
- Risk: medium. Stale articles on a short TTL are acceptable but provenance `retrieval_time` must stay the original fetch time, not the cache hit time, and the record must be tagged as cached. Changing which snippets skip extraction changes `extraction_status` and quality scores, so avoid unless approved.

### B11. Cold start and imports
- MEASURED (warm cache): `python -m finai --help` total 0.71 s wall; `import finai.__main__` is ~7 ms (lazy). Importing `app.core.agent_loop.runtime` costs ~556 ms: tool_runner ~369 ms, of which `quant.fundamentals` triggers 172 ms (that module pulls `quant/__init__` -> technical_engine -> pandas 188 ms + pandas_ta_classic ~165 ms + talib). `yfinance` import ~0.12 s (imported at module top of data/providers/yfinance.py:28 but only when resources are built).
- Fix: lazy-import `pandas_ta_classic` inside the two methods that use `pta.kc/cmf` (technical_engine.py:~334-345), and make `quant/__init__.py` not import the engine eagerly. Saves ~0.17-0.3 s on every process start. Importing pandas can't be avoided on the report path, but could be deferred until the first analysis tool runs if `--help` / session start latency matters (bridge startup).
- Risk: very low, no output change.

### B12. Quant compute (not a bottleneck)
- MEASURED: `TechnicalEngine.analyze` on 252 synthetic daily bars: 4.6-7.4 ms per call (warm), already vectorised via talib/numpy (technical_engine.py:134-160). It is called through `asyncio.to_thread`, fine. `pd.DataFrame(rows)` rebuild from dict records per call (tool_runner.py ~670) is negligible. `FundamentalScanner` is dict arithmetic. No repeated recomputation seen except scan + overview both calling `analyze` on the same rows (7 ms; could cache by (key, len(rows)), not worth it).

### B13. Provider quota bookkeeping on the hot path
- app/core/quota.py:29-70: every request opens a sqlite connection, runs DELETE + 1-3 COUNTs + INSERT + COMMIT (fsync). ~2-10 ms per request on SSD, more on slow disks; called once per Upstox request (x8 for fundamentals) and per TinyFish query. REASONED, minor. Fix: `PRAGMA journal_mode=WAL; synchronous=NORMAL`, reuse the connection. Risk low.

### Ticker search cost
- Deterministic parsing is regex-only (instrument_resolution.py), cost negligible. The remote cost is the Upstox search (B6) when the query has no explicit `.NS`/`.BO` symbol; there is no yfinance search. No cross-session cache of name -> ticker; add a small persisted cache (e.g. `.finai/` JSON with TTL days) for resolved names to skip the call on repeat queries. Risk: stale mapping after symbol changes; use a TTL of days and only cache `resolved` status.

## 3. Quick wins vs larger refactors

Quick wins (small, low risk, no output change):
1. B6: move instrument resolution off the event loop (`to_thread`) and set a short search timeout.
2. B4a: Upstox-first for `run_fundamental_scan`, yfinance only as fallback (saves a discarded 1-4 s call). Keep the scan-path semantics noted above.
3. B3: thread the 8 Upstox fundamentals endpoints, one shared `httpx.Client`.
4. B7 (key part only): normalise cache keys with `Ticker.cache_key`.
5. B11: lazy `pandas_ta_classic` import (about 0.17-0.3 s startup).
6. B9: do not retry `TimeoutError` on `Ticker.info`; shorter Upstox timeout for small endpoints.
7. B2 (client part): reuse one `httpx.AsyncClient` in `TinyFishSearchClient`.

Larger refactors (more risk, bigger payoff):
1. B1: concurrent execution of independent tool calls in runtime.py (biggest win; needs ordering and shared-state care; coordinate with the orchestration auditor).
2. B2: concurrent TinyFish queries, which first needs a rate-limit-aware scheduler because the 2 req/s local quota raises instead of waits.
3. B10: persistent news/article cache with provenance preserved (original retrieval_time, cached flag) and a cross-process OHLCV/fundamentals disk cache (parquet/JSON in `.finai/`, TTL as in tool_runner.py:247-249). Treat `.finai/` as sensitive per repo rules.
4. B5: decouple news from the fundamentals cache when parallelising.
5. Provider circuit breaker shared across Upstox/yfinance/TinyFish to cut failure latency (B9).

Not verified (no live runs allowed): all network timings above are estimates; confirm with the existing `last_run_stats` fields (`connector_elapsed_ms`, `extraction_elapsed_ms`) and tool `duration_ms` diagnostics (`FINAI_DIAGNOSTICS`, runtime.py:1245) on a real report before prioritising B1 vs B2.
