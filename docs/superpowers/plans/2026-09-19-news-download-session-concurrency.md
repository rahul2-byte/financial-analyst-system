# News Download and Session Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep synchronous article downloads off the event loop, stop oversized downloads while streaming, and serialize concurrent HTTP requests for one local session.

**Architecture:** `ArticleExtractor` remains synchronous but reads response chunks through `httpx.stream`, enforcing `MAX_ARTICLE_BYTES` before accumulating more data. `NewsPipelineRunner` invokes that bounded synchronous extractor with `asyncio.to_thread`. The HTTP route uses one process-local `asyncio.Lock` per storage session, covering history mutation and the complete streamed run; different sessions remain concurrent.

**Tech Stack:** Python 3.11+, asyncio, httpx, pytest/pytest-asyncio, FastAPI route helpers, local `SessionStore`.

**Spec:** User request in the active conversation.

## Global Constraints

- Preserve existing source-quality, redirect, and failure behavior.
- Do not add a queue, database, provider, model, or paid API.
- Enforce the download limit while iterating response bytes.
- Keep negative results visible as snippet-only or failed requests.
- Serialize requests sharing one local HTTP session; do not serialize unrelated sessions.

## Review Focus

- Slow synchronous extraction must not block another coroutine on the event loop.
- A response exceeding the byte limit must stop iteration before the full body is read.
- Redirects must be checked and bounded rather than bypassing URL safety.
- HTTP and transport failures must continue to produce safe extraction failure behavior.
- Two requests for one session must not concurrently mutate transcript/session state.

### Task 1: Bounded article download and async runner boundary

**Files:**
- Modify: `backend/data/news_pipeline/extractor.py`
- Modify: `backend/data/news_pipeline/runner.py:76-118`
- Test: `backend/tests/unit/test_news_pipeline_extractor.py`
- Test: `backend/tests/unit/test_news_pipeline_runner.py`

- [ ] Add tests for streamed byte-limit rejection, redirects, failed sources, and runner event-loop responsiveness.
- [ ] Run those tests and observe the expected failures.
- [ ] Change `_safe_get` to use `httpx.stream`, accumulate only bounded chunks, and preserve redirect/HTTP failure handling.
- [ ] Run the focused tests and then the news pipeline tests.

### Task 2: Per-session HTTP execution rule

**Files:**
- Test: a focused session concurrency test.

- [ ] Add a concurrent same-session test with a blocking fake runtime and assert maximum active runs is one.
- [ ] Run it and observe the expected overlap failure.
- [ ] Add a process-local lock registry keyed by hashed storage session and hold the lock across session load, message append, runtime streaming, and completion.
- [ ] Run the focused test and existing session tests.

### Final verification

- [ ] Run changed-file Ruff checks and formatting checks.
- [ ] Run `uv run mypy backend/`.
- [ ] Run `uv run pytest backend/tests`.
- [ ] Preserve and report any existing warnings or unrelated formatting failures.
