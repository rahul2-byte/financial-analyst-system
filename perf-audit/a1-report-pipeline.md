# A1: Report pipeline speed audit (orchestration / LLM side)

Scope: bridge request -> routing -> AgentLoop -> provider -> publication -> bridge notify.
Evidence labels: [M] measured here, [R] reasoned from code. No LLM/network calls were made, so per-call latencies are not measured; wall-clock figures are estimates from code structure and configured timeouts.

## 1. Request flow map

1. `finai/bridge/server.py:268 _run_start` creates a task; `:283 _run` iterates `repl.typed_stream(query)` and, per event, runs `reduce_event` + `build_display` then `await writer.notify("run.event")` (`:296-306`). After the stream ends, `_report_for` -> `build_report_view` (`:342`, `finai/report_view.py`) builds the structured view and sends it once in `run.finished` (`:330-340`).
2. `finai/session.py:_agent_loop_stream` (`:117`) appends user message to the JSONL transcript, runs `_compact_history` (`context_budget.py`, deterministic, no LLM), then `ResearchRunner.stream`. For every event it calls `store.append_trace_event` (`:158`), which opens the ledger file and fsyncs for all non-delta events (`app/events/ledger.py:37-65`).
3. `finai/session_runtime.py:89 ResearchRunner.stream`: instrument resolution (`:327`, deterministic), `routing_policy.decide` (`:122`), then branches (clarification / direct tool / deny), otherwise builds a new `AgentLoop` per turn (`:290`).
4. `app/services/routing_policy.py:51 decide`: deterministic safety + regex routes (`:164`); anything else makes a Jev LLM HTTP call (`app/services/jev_service.py:108`, timeout 10s, 1 retry).
5. `app/core/agent_loop/runtime.py:259 _run`: builds system prompt + skills + report schema (`:277-320`), emits RunStarted/Route events, then the round loop `for round_number in range(1, max_rounds=12)` (`:456`).
   - Each round: `_stream_model` (`:1585`) -> `ModelStreaming.stream` (`model_streaming.py`) -> `OpenRouterService.generate_stream` (`openrouter_service.py:784`, `_stream_request :303`).
   - If the assistant message has tool calls: **sequential** `for call in assistant.tool_calls` (`runtime.py:1081`), each `await tool_executor.execute(...)` (`:1231`), then a Jev `decide` "evidence checkpoint" LLM call (`:1414`) before the next model round.
   - If no tool calls and `publish_reports`: parse + validate draft (`:~800-1000`); on failure append repair instruction and `continue` (another full model round, up to `max_report_repairs=2`, 120s timeout each).
6. Provider call end: `provider_archive.store` (sync file write, `openrouter_service.py:637`), `ModelCallTrace` JSONL with fsync (`model_call_trace.py:63-84`).

Typical report LLM sequence: Jev route (1) -> model round 1 (tool calls only, max 1024 tokens) -> tools (sequential) -> Jev checkpoint (1) -> [model round 2 (more tools?) -> tools -> Jev checkpoint] -> final report round (max 32768 tokens, structured JSON) -> [repair rounds 0-2]. That is 3 to 7 serial LLM calls before the user sees a report.

## 2. Ranked bottlenecks

### B1. Report text is never streamed; the user sees nothing during the longest call [R], impact HIGH (perceived), MED (actual)
- `runtime.py:~515-520`: `if not structured_output and not review_gate: yield item`. For `answer_contract == "report"|"lookup"` the TextDeltas are swallowed; the final report is only emitted after full generation and validation (`:720-760`, `:1060`), and the structured view only arrives at `run.finished` (`bridge/server.py:330`).
- The final round has `max_tokens=32768` (`model_streaming.py`, `config/models.py:44`). A multi-thousand-token JSON report at typical Haiku-class speeds is plausibly 30-90s of dead air.
- Fix: stream partial output to the UI. Options, cheapest first: (a) emit the existing `StageStarted`/progress events plus a token counter ("drafting report, N tokens") from the swallowed deltas; (b) incrementally parse the JSON draft (e.g. section keys as they close) and emit `report.section` events that the frontend renders progressively, with the validated full view still replacing them at `run.finished`; (c) have the model write markdown sections and validate afterwards. Risk: (b)/(c) show unvalidated text that may fail fact-check/repair; label as "draft" and replace. Needs frontend contract change (`docs/frontend.md`, `gen:types`).

### B2. Tool calls within a round run sequentially [R], impact HIGH
- `runtime.py:1081` loop with `await tool_executor.execute` at `:1231`. A report typically needs stock data, fundamentals, technical overview, news. `news:fetch_news` has a 120s timeout override (`tool_execution.py:21`) and the news pipeline budget is 60s (`NEWS_PIPELINE_TOTAL_TIMEOUT`), so one slow news call blocks quick tools and the clock toward `max_run_seconds=150`.
- Fix: when a round contains several independent evidence tool calls, run the execute step with `asyncio.gather` (or TaskGroup) and then process results in original order (history append, evidence accounting, events). Keep `ask_user`, approval, duplicate-signature and emergency-ceiling checks in a serial pre-pass. Per-tool `ToolStarted` events can be emitted up front. Risk: medium; the loop body mixes control flow (`break`/`return` on clarification, safety, duplicate) with execution, so split into prepare / execute / reduce. `FinancialToolRunner` shares caches (`_ohlcv_by_request`, `turn_facts`) that are plain dicts, which is fine under asyncio but `to_thread` calls to yfinance should be checked by the data audit for thread safety. Expected savings: roughly (sum of tool times) - (max tool time), commonly 10-40s when news is included.

### B3. Round 1 is a pure "choose tools" LLM call for a deterministic fan-out [R], impact HIGH
- For `intent=research_report` with a resolved ticker, the tool set is essentially fixed. Instead the flow pays Jev route + model round 1 (up to 1024 tokens, TTFT + generation) + Jev checkpoint before any data is fetched.
- Fix: when route is REPORT_SYNTHESIS and `resolution.status == "resolved"`, prefetch the standard evidence set (stock data, fundamentals, technical, news) concurrently right after routing (or even concurrently with the Jev call), inject results as synthetic assistant tool_calls + tool messages (the resume path at `runtime.py:~489 resumed_assistant` shows the loop already supports a pre-seeded assistant), and go straight to the report round. Saves 1 model round, 1 Jev checkpoint, and serializes nothing. Risk: medium-high; changes the "model decides tools" contract and eval baselines; keep model-driven rounds available for gaps (e.g. peers/comparison). Gate behind a flag first.

### B4. Jev controller checkpoint after every tool round [R], impact MED-HIGH
- `runtime.py:1405-1427`: `decision_provider.decide` (HTTP, 10s timeout, 1 retry, `FINAI_ROUTER_TIMEOUT_SECONDS`, `config/models.py:22-23`) is awaited after each tool round, before the next model round. It is "advisory" (exception -> ignored, `:1450`) yet blocks the critical path. Worst case adds ~20s per checkpoint on a slow router; normal case one extra RTT plus inference per round.
- Fix: (a) skip when all required tools succeeded and evidence is sufficient deterministically (`evidence.availability` already tracks this); (b) run it concurrently with the next model round and only act if it returns DENY/ASK before the model finishes (cancel on completion); (c) lower timeout to ~3s. Risk: low for (a)/(c); medium for (b).

### B5. Initial Jev routing LLM call before any work [R], impact MED
- `routing_policy.py:88` -> `jev_service.py:108`. Runs for any query not matched by the three narrow regexes (`:164-216`), i.e. every report request. Up to 10s timeout, retry on 429/529 only after `sleep(0.1..0.5)`, and a fresh transport error retry.
- Fix: for queries matching `_wants_report` (`session_runtime.py:48`) with a resolved instrument, take the deterministic REPORT_SYNTHESIS route and skip Jev (the code already overrides Jev results to this at `routing_policy.py:116-137`), or start the Jev call and tool prefetch (B3) concurrently and only apply Jev result for deny/clarify. Also lower timeout. Risk: medium (safety routing semantics; deterministic injection guard at `:64` stays).

### B6. Prompt caching not used; full prompt resent each round [R], impact MED
- `openrouter_service.py:314-326`: payload has no `cache_control`; each round resends system prompt (~1.1k chars) + skills (2 x ~0.5k) + report schema (2k chars) + tool defs (3.2k chars JSON) + growing tool results (each capped at 7,500 chars, `runtime.py:2078`). [M] static prompt material is small (~7-8k chars total, roughly 2k tokens), so this is not the dominant cost; input bloat mainly comes from tool results (<= ~5 x 7.5k chars) and from repair rounds that re-carry the draft.
- Fix: add `cache_control` breakpoints on the stable prefix when the selected model supports it; trim tool JSON to the fields the report schema needs (`extract_evidence_facts` already derives facts, so the model could receive facts instead of raw payload). Risk: low for caching; medium for trimming because grounding checks reference tool content.

### B7. Repair rounds are full serial LLM calls with 120s timeouts [R], impact MED (tail latency)
- `runtime.py:~960-1040`, `max_report_repairs=2`, `OPENROUTER_REPAIR_TIMEOUT=120`, repair `max_tokens=8192`. A failed fact-check costs another full generation round, so the tail is 2-3x the base time.
- Fix: patch-style repair (ask only for failing sections / fact ids), deterministic auto-fix for unreferenced fact markers (`unreferenced_fact_markers` already identifies them), shorter repair timeout (~45s). Also log repair frequency from existing traces to see how often this triggers [needs data; not measured]. Risk: medium.

### B8. Cold start of `python -m finai` [M], impact MED (per launch, 0.75s wall)
- `-X importtime`: `finai.cli` cumulative 603 ms; `finai.session_runtime` 360 ms; `app.core.agent_loop.tool_runner` 307 ms; `pandas` 169 ms; `quant.technical_engine` 134 ms (of which `pandas_ta_classic` 128 ms, numba 104 ms); `pydantic_settings`/`app.config` 106-118 ms; `app.core.resources` 140 ms. `time ... --help` = 0.756 s wall, 3.25 s user (multi-threaded import).
- Cause: `tool_runner.py` imports `quant.fundamentals`/`technical_engine` -> pandas, pandas_ta_classic, numba at module import, and `finai.cli` imports `session` -> `session_runtime` eagerly even for `--help` or when the bridge only needs to answer `initialize`.
- Fix: lazy-import `quant.*`/pandas_ta inside the tool handlers (first technical call), and lazy-import `finai.session` in `cli.py`/`bridge/__main__.py` so `initialize` returns before heavy imports finish (or warm in a background thread while the UI draws). Risk: low. Note interaction with the data/quant audit: first technical call then pays ~130-250 ms on the event loop thread unless imported via `to_thread` warmup.

### B9. Synchronous file I/O in the event loop on the hot path [M+R], impact LOW-MED
- Per run event: `ledger.append` opens file, `json.dumps` twice, fsync on non-delta events (`ledger.py:52-64`); [M] fsync ~1.4 ms on this disk, so ~100 events = ~0.15 s total. `ModelCallTrace.write` fsyncs on every record including `request.attempt` with full request body (`model_call_trace.py:63-84`, `jev_service.py:150`). `ProviderArchive.store` pretty-prints (`indent=2`) the full raw chunk list for each model call (`provider_archive.py:48-52`, called from `openrouter_service.py:637`); [M] 3,000 events took 41 ms, blocking the loop at the end of each call (larger on bigger streams). `write_checkpoint`/`persist_message` are sync too.
- Also `await asyncio.sleep(0)` per token (`openrouter_service.py:576`) and a per-token `chunk_timings` dict (`model_call_trace.py:~136`) add small overhead.
- Fix: move archive/trace writes to `asyncio.to_thread` or a single background writer queue; drop `indent=2` and make the archive opt-in (only needed for replay/eval); fsync only on `run.completed`/`call.failed`. Risk: low; durability semantics documented in `ledger.py` comment ("must survive a cancelled process") must be preserved at run boundaries.

### B10. Per-turn construction / duplicate work [M], impact LOW
- `PromptRegistry.bundled()` [M] 6.8 ms first load (pure-Python YAML `_UniqueLoader`), then 1 us (cached); `SkillRegistry.bundled()` [M] 3.6 ms. They are loaded in `resources.py:48-49` once, but `session_runtime.py:119,254,277,886` and `context_budget.py:84` fall back to `bundled()` / `PromptRegistry.bundled()` per call if `resources.skills/prompts` is None; in production they are set, so only a cleanliness issue. `AgentLoop` and `FinancialToolRunner.definitions()` (`tool_runner.py:343`, `deepcopy` of tool definitions each round via `_tool_definitions`) and `ReportDraft.model_json_schema()` [M] 0.7 ms are recomputed per turn/round; negligible.
- Caches that exist: OHLCV 60s/900s, fundamentals 3600s TTL (`tool_runner.py:247-316`), per-session (the `FinancialToolRunner` lives in `ResearchRunner` per session, so caches die with the process). Not cached: `news:fetch_news`, Jev route for repeated identical queries, the final report for an identical repeated request in the same session. Fix: cache news with a short TTL (5-10 min) and an identical (query, ticker, evidence-hash) report result; risk: stale data, so only within a short TTL and keyed on data timestamps.

### B11. Timeouts and retries that add latency [R], impact LOW-MED (tail)
- `OPENROUTER_MAX_RETRIES=2`, backoff 0.5-4s, total budget `OPENROUTER_TIMEOUT=600s` (`config/models.py:33-40`) but run-level `FINAI_AGENT_MAX_RUN_SECONDS=150` + 12s wrap-up bound the whole run, so a run can burn the entire budget on a stalled provider; `OPENROUTER_READ_TIMEOUT=60` means a hung stream is only detected after 60s of silence. Circuit breaker opens at 3 failures (30s recovery). Native OpenRouter `models` fallback array is used, which is good (`openrouter_service.py:326`).
- Fix: shorter read timeout for first byte (e.g. 20s) with retry on the fallback model; hedge: start fallback after N seconds of no first token. Risk: low-medium (cost on duplicate calls).

## 3. Quick wins vs larger refactors

Quick wins (hours, low risk)
- B8 lazy imports (pandas/pandas_ta/numba and `finai.session` in the bridge path): ~300-450 ms off cold start.
- B9 drop `indent=2`, move archive + trace writes off the loop, fsync at run boundaries only.
- B4(a)/(c) skip or shorten the Jev checkpoint when evidence is already sufficient/all tools succeeded; cut Jev timeout to ~3s.
- B1(a) emit a progress/token-count event from the swallowed report deltas so the UI shows liveness (full partial-section streaming is the bigger item).
- B7 shorter repair timeout; B6 add `cache_control` where supported.

Larger refactors (days, medium risk, biggest payoff)
- B2 parallel tool execution within a round (split prepare/execute/reduce in `runtime.py:1081-1330`).
- B3 deterministic evidence prefetch for `research_report` with resolved ticker, skipping model round 1 and the checkpoint; combine with B5 (skip/parallelize Jev route). Together B2+B3+B4+B5 remove roughly 2-4 serial LLM round-trips and serialize no tool time: my estimate is 20-50% of end-to-end time, to be confirmed with real traces (`.finai` trace timings via `ProviderCompleted.duration_ms`/`first_token_ms`, `RunCompleted.duration_ms`).
- B1(b) progressive section streaming of the structured report (needs frontend contract + gen types update).
- B7 patch-style repair of failing sections only.

## 4. Interaction points with other audits
- Data/quant agent: tool handlers are awaited serially by the loop (B2), so per-tool latencies add; `news:fetch_news` (60s pipeline budget / 120s tool timeout) is the largest single tool. Heavy `quant`/pandas_ta import cost lands in `tool_runner` import (B8).
- Frontend agent: report appears only at `run.finished` (`bridge/server.py:330-340`) with `build_report_view` computed after the stream; `report_view.py` (608 lines) is pure CPU after the last token. Any progressive section protocol (B1b) needs a new notification type and `npm run gen:types`.

## 5. Not measured / caveats
- No live LLM or tool timing was possible (no network/paid calls). Impacts are structural estimates; validate with a real trace of one report run (per-event `occurred_at` in the `.finai` ledger gives stage durations without extra cost).
- Not checked: `finai/display.py`/`state.py` per-event cost, `report_view.py` CPU time, `data/` and frontend internals (other audits).
