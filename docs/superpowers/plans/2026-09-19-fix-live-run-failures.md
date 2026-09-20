# Live Run Failure Recovery Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task-by-task. Do not commit unrelated pre-existing worktree changes.

**Goal:** Make failed Hive streams observable and bounded, retain relevant news aliases without weakening source-quality policy, and make approved replay represent the same multi-round workflow as the live run.

**Architecture:** Keep the existing AgentLoop, provider, news pipeline, and replay boundaries. Fix failure signaling at `HiveService`, reuse the existing company-alias vocabulary in news relevance checks, and extend replay input minimally with an optional ordered model-stream sequence while preserving the current single-snapshot format.

**Tech Stack:** Python 3.11+, async generators, httpx `MockTransport`, Pydantic event models, pytest, existing provider archives.

**Spec:** Current-run diagnosis recorded in the task conversation and artifacts under `.finai/sessions/f50d2ece9c8249fc8d2ba4d2f9d0a76b/`.

## Global Constraints

- Do not call live or paid providers during implementation or tests.
- Do not add dependencies, queues, databases, or unrelated architecture.
- Preserve failed, partial, empty-news, and missing-snapshot outcomes; never turn them into successful fixtures.
- Keep the existing total Hive request budget and pre-stream retry policy unless a test proves a specific regression.
- Keep source-quality filtering enabled by default; improve only entity relevance matching.
- Preserve backward compatibility for existing single `model_stream` replay cases.
- Do not modify resume files or commit the dirty worktree.

## Review Focus

- A stream that sends headers or reasoning but never sends `[DONE]` must emit a typed provider failure before the run failure, with timeout and partial-output state.
- A transport failure at the request deadline must not lose the underlying timeout type in `HiveProviderError`.
- `HDFC BANK LTD`, `HDFC Bank`, `HDFCBANK`, and `HDFCBANK.NS` must resolve to the same relevance entity, while unrelated companies remain irrelevant.
- Empty or low-quality news must remain an evidence failure; alias matching must not bypass source tiers, extraction status, recency, or quality thresholds.
- Replay must reject missing or exhausted model-stream sequences and must accept the recorded `news_pipeline/fetch_news` snapshot provider without network access.

### Task 1: Make Hive stream failures explicit and bounded

**Files:**
- Modify: `backend/app/services/hive_service.py` in `_stream_request`
- Test: `backend/tests/unit/test_hive_service.py`

**Interfaces:**
- Preserve the existing event names and payload shape: `provider_failed` must continue to contain `attempts`, `phase`, `message`, `model_id`, `duration_ms`, `timeout`, `partial_output`, and `usage`.
- Preserve `HiveProviderError` as the raised provider exception.

- [ ] **Step 1: Add a failing stalled-stream test.**

  Use `httpx.MockTransport` with an async byte stream that emits one valid SSE line, then sleeps past a very small `HiveRetryPolicy.total_budget_seconds`. Assert that `_stream_request` raises `HiveProviderError`, the message names `TimeoutError` or `request budget exhausted`, and the collected events include exactly one terminal `provider_failed` event with `timeout=True` and `partial_output=True`.

- [ ] **Step 2: Add a failing deadline-before-retry assertion.**

  Exercise a transport exception after the response has started and assert that no `provider_retrying` event is emitted after stream start. This pins the rule that a partially started SSE response is terminal for that request.

- [ ] **Step 3: Implement the minimum state tracking.**

  Track `stream_started` separately from public-token and tool-call counters. In the timeout/transport handler:

  ```python
  partial_output = stream_started or streamed_token_count > 0 or emitted_tool_call
  failure = {
      "attempts": attempt,
      "phase": "transport",
      "message": type(exc).__name__,
      "model_id": self._model(model),
      "duration_ms": latency_ms,
      "timeout": isinstance(exc, (TimeoutError, httpx.TimeoutException)),
      "partial_output": partial_output,
      "usage": usage,
  }
  yield {"event": "provider_failed", "data": failure}
  ```

  Emit that event before raising when the deadline prevents retry. Do not retry after `stream_started`; retain current retries only for failures before a response starts. Raise a stable message such as `Hive transport failure: TimeoutError` instead of interpolating an exception whose string may be empty. Keep telemetry `timeout`, `partial_output`, and duration consistent with the emitted event.

- [ ] **Step 4: Run the focused Hive tests.**

  Run:

  ```bash
  UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_hive_service.py --no-cov
  ```

  Expected: all existing and new Hive tests pass; no live HTTP request is made.

### Task 2: Retain relevant common-name news while preserving quality gates

**Files:**
- Modify: `backend/data/news_pipeline/extractor.py` and `backend/data/news_pipeline/replay.py`
- Test: `backend/tests/unit/test_news_pipeline_extractor.py`, `backend/tests/unit/test_news_pipeline_runner.py`, and `backend/tests/unit/test_news_pipeline_replay.py`

**Interfaces:**
- Keep `ArticleExtractor.extract(...)` and `ReplayArticleExtractor.extract(...)` call signatures unchanged.
- Keep `NewsPipelineRunner.min_quality_score`, source tiers, extraction scoring, and default filtering unchanged.

- [ ] **Step 1: Add the failing alias-relevance tests.**

  Add extractor cases asserting that text containing `HDFC Bank` is relevant for `company_name="HDFC BANK LTD"` and `ticker="HDFCBANK.NS"`, while text naming a different issuer remains irrelevant. Add the same assertion for `ReplayArticleExtractor`.

- [ ] **Step 2: Add the failing quality-gate regression test.**

  Feed a common-name HDFC Bank snippet through the runner with a deterministic snippet-only extractor and assert that relevance is true. Keep a separate low-quality/irrelevant case asserting that the default quality filter still returns no record.

- [ ] **Step 3: Implement alias matching without lowering quality thresholds.**

  Update both extractor relevance checks to use the same normalized entity forms already used by `derive_company_aliases`: full company name, legal-suffix-stripped company name, ticker, and ticker without exchange suffix. Match aliases as bounded phrases, not arbitrary substrings. Do not use relevance matching as semantic source support; it only determines whether an article is about the requested entity.

- [ ] **Step 4: Run focused news tests.**

  Run:

  ```bash
  UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest \
    backend/tests/unit/test_news_pipeline_extractor.py \
    backend/tests/unit/test_news_pipeline_runner.py \
    backend/tests/unit/test_news_pipeline_replay.py --no-cov
  ```

  Expected: existing redirect, size-limit, failed-download, quality-filter, and replay tests remain passing.

### Task 3: Make provider replay match recorded multi-round runs

**Files:**
- Modify: `backend/app/core/resources.py`, `backend/app/core/agent_loop/replay.py`, `backend/data/news_pipeline/replay.py`, and `evals/offline.py`
- Test: `backend/tests/unit/test_replay_provider.py`, `backend/tests/unit/test_news_pipeline_replay.py`, and `backend/tests/unit/test_offline_evaluation.py`

**Interfaces:**
- Existing case shape remains valid:

  ```json
  {"replay_snapshots": {"model_stream": "<sha256>"}}
  ```

- Add an optional ordered form for multi-round runs:

  ```json
  {"replay_snapshots": {"model_streams": ["<sha256-round-1>", "<sha256-round-2>"]}}
  ```

- `ReplayModelStream` consumes one snapshot per `generate_stream` call, raises a clear `replay model stream exhausted` error when the sequence is too short, and continues supporting a single string hash.
- `ReplayNewsConnector` accepts both existing `yfinance/fetch_news` snapshots and recorded `news_pipeline/fetch_news` snapshots, while still rejecting mismatched operations and malformed payloads.

- [ ] **Step 1: Add failing replay tests.**

  Test that two ordered model hashes produce two sequential streams and a third call fails explicitly. Test that a `news_pipeline/fetch_news` list snapshot is accepted and still performs no URL fetch. Test that `validate_cases` accepts `model_streams` and rejects malformed or empty sequences.

- [ ] **Step 2: Implement backward-compatible replay normalization.**

  Normalize `model_stream` to a one-item sequence when `model_streams` is absent. Validate every hash with the existing SHA-256 rule. Pass the sequence into `ReplayModelStream`, increment an internal call index, and load the corresponding immutable archive entry for each call. Expand the allowed replay-key set without changing other case requirements.

- [ ] **Step 3: Correct the news provider check.**

  In `ReplayNewsConnector`, accept `provider == "news_pipeline"` for `operation == "fetch_news"`; retain `yfinance` compatibility for existing fixtures. Keep strict replay behavior so missing or incompatible snapshots remain failures.

- [ ] **Step 4: Run focused replay/offline tests.**

  Run:

  ```bash
  UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest \
    backend/tests/unit/test_replay_provider.py \
    backend/tests/unit/test_news_pipeline_replay.py \
    backend/tests/unit/test_offline_evaluation.py --no-cov
  ```

  Expected: existing immutable-artifact and missing-snapshot negative tests remain passing, and no replay test contacts a provider.

### Task 4: Verify the complete local surface

- [ ] Run the focused tests from Tasks 1–3 together.
- [ ] Run local checks for `/`, the direct health route with stubbed dependencies, and the CLI runtime; do not call Hive, TinyFish, Upstox, or YFinance.
- [ ] Run `uv run ruff check backend/ evals/`, `uv run mypy backend/`, `PYTHONPATH=. uv run python -m evals.validate`, CLI smoke checks, and the full backend tests with and without coverage.
- [ ] Inspect `git diff --check`, changed paths, and test output. Preserve the original failed run artifact and record any remaining HTTP health probe limitation rather than replacing it with a successful fixture.

## Explicit non-goals

- No live-provider retry tuning based on a single run.
- No source-rights approval, human semantic labels, or claims that alias/reference validation establishes truth.
- No change to the quality threshold merely to retain news.
- No automatic fallback from a failed live run to a successful replay result.
- No resume, commit, push, dependency installation, or unrelated architecture change.
