# A3: Frontend (Ink) + bridge speed audit

Measured on this machine (Node 26.13, Python 3.12 venv, warm disk cache). "Measured" = I ran it; "Reasoned" = from reading code. No LLM calls were made. `npm run build` was run once via `node esbuild.config.mjs` (rewrote the gitignored `frontend/dist/cli.js`). Note: `npm` fails under zsh here (`_nvm_lazy_load` shim); use `bash`.

## 1. Map: startup and request/stream flow

Startup
- `frontend/src/cli.tsx:99` calls `render(<App/>)` immediately. The UI paints before the bridge exists (no blocking wait). Measured: `node dist/cli.js --version` = ~0.30s wall (1.1 MB unminified bundle, `esbuild.config.mjs` has `minify:false`, no bytecode/compile cache).
- `src/ui/hooks/useBridge.ts:275-277` spawns the bridge eagerly in a `useEffect` after first render. `process.ts:171` spawns `.venv/bin/python -m finai.bridge`, falling back to `uv run --project` (process.ts:84-92, slower: uv resolve each launch).
- Python `backend/finai/bridge/__main__.py:105-120` -> `server.py:18-25` imports `finai.report_view` -> `app.core.agent_loop.publication` -> pandas etc. BEFORE the protocol loop reads stdin. Measured: `import finai.bridge.__main__` = ~0.69s (importtime: server 406ms, protocol/`app.events.models` 170ms, report_view 376ms, agent_loop.tool_runner 315ms, pandas ~150ms).
- `initialize` (`server.py:248-266`) then builds `FinAIRepl` (imports `finai.session` -> `session_runtime`, `quant.technical_engine`/`pandas_ta_classic` ~200ms). Measured spawn -> initialize response = 0.74-0.84s (3 runs). So first paint ~0.3s, "ready" ~1.1s after launch.
- Header/session title appear only after `onConnected` (App.tsx:~400). Typed input before ready is OK: `bridge.ensure()` returns the pending promise.

Request/stream
- Submit -> `startRun` -> `run.start` RPC (accept only, 5s timeout, client.ts:25) -> Python `_run_start` (server.py:268) spawns a task -> `_run` (server.py:283) iterates `repl.typed_stream`, for each event: `reduce_event` + `build_display` + pydantic `model_dump` + `writer.notify` (flushed per line, framing.py:136-140; `FdWriter` is blocking `os.write` on the event loop, __main__.py:23-28).
- Node: `framing.ts` LineReader (Buffer concat, 8 MiB cap) -> `JSON.parse` per line (client.ts:247) -> `client.on('run.event')` (App.tsx ~415) -> `RunCollector.onEvent` -> `store.dispatch` (store.ts:68) -> throttled 33ms notify -> `useSyncExternalStore` in `App` (App.tsx:337).
- Nothing is committed to scrollback during a run (`RunCollector.liveText` App.tsx:156 just returns the full draft). At `run.finished` (`server.py:333-346`) the structured `report` is attached once; `onFinished` (App.tsx:~170) commits trail + report + footer in one go.
- Cancel exists: Esc/Ctrl+C -> `cancelRun` (App.tsx:~575) -> `run.cancel`. Elapsed time + spinner exist (`useElapsed.ts`, `LiveActivity.tsx`).

## 2. Ranked issues

### #1 No incremental result display: the report appears only at the very end (perceived speed, biggest)
- Where: `server.py:333-346` (report built only in `finally` after the stream), `App.tsx:156` + `App.tsx:236-240` (single commit at end), `runtime.py:529-556` (backend, interaction point: `TextDelta` is NOT yielded when `structured_output` or when `review_gate = not structured_output and review_enabled`).
- Evidence: reasoned from code. For structured-report runs or runs with output review on, the user sees only spinner + tool labels until the final frame, however long the LLM takes. Also doc drift: `docs/frontend.md:77` says complete Markdown blocks are committed while streaming; code does not (App.tsx:152-156 says "nothing is committed while a run is active").
- Impact: High. Wall time unchanged, but the user stares at a spinner for the whole LLM phase.
- Fix: (a) emit partial structured data as soon as evidence is ready (e.g. a `run.partial` / `report.section` notification: key figures + signals from deterministic quant, which exist before synthesis), render them as committed Static items; LLM prose fills in after. (b) For freeform answers, commit completed Markdown blocks as they stream (what the docs describe) and keep only the open tail live. (c) Decide whether the review gate must hold text (interaction with the LLM-orchestration audit).
- Risk: Medium. Protocol change (docs/frontend.md contract + `gen:types`), and must not show unreviewed model text if the safety gate is meant to withhold it. Deterministic figures are safe to show early.

### #2 Whole `App` re-renders every 100ms during a run, re-lexing + re-laying-out the entire live draft each time
- Where: `useElapsed.ts:71` (setInterval 100ms setNow in App's own state, `App.tsx:352`), `App.tsx:651-688` (liveText/Answer/Composer/StatusLine all re-rendered), `Answer.tsx:25` -> `markdown.tsx:511-514` (`marked.lexer` over full text every render), no `React.memo` anywhere (grep: zero hits in src).
- Evidence: measured. Full render (lexer + Ink layout) via `renderToString` of the Answer: 552 chars 9.9ms, 3.3k chars 9.4ms, 6.6k chars 21.7ms per frame (noisy, includes JIT warmup). At 10Hz tick + 30Hz delta notifications this is up to ~30 full re-lex/layouts per second, cost O(n) per frame so O(n^2) over a run. Fine for short answers, 20-70% of a core for long ones; also each Ink frame rewrites the full live region (non-incremental, `cli.tsx:99` doesn't set `incrementalRendering`), so a tall live draft flickers.
- Impact: Medium-high on long answers / slow terminals (tmux, SSH); also input lag (Composer re-renders with everything).
- Fix: (1) move the spinner/elapsed into the `LiveActivity` component (own state/interval) so ticks do not re-render App; (2) `React.memo` Composer, StatusLine, and a `StreamingAnswer` keyed on text; (3) memoize committed-block render and only lex the open tail (commit-complete-blocks, see #1 (b), solves this structurally); (4) lower spinner tick to ~80-120ms only inside LiveActivity, elapsed to 1s; (5) try `render(..., { incrementalRendering: true })` (Ink 6.8 option, `render.d.ts:64`).
- Risk: Low for 1-3; (5) needs visual check in the xterm snapshot tests.

### #3 Python import cost serialized before the first byte of protocol (about 0.7s of the ~1.1s to ready)
- Where: `server.py:21-24` top-level imports of `finai.context_budget`, `finai.report_view` (-> `app.core.agent_loop.publication` -> pandas, tool_runner, quant), `finai.display`, `finai.state`; `bridge/__init__.py:3` imports `protocol` (-> `app.events.models` 170ms). The comment at `__main__.py:48` ("heavy import happens only on demand") is only true for `finai.session`; the bridge module itself already pulls most of it.
- Evidence: measured. `-X importtime`: `finai.bridge.__main__` 589ms cumulative; `finai.report_view` 376ms; pandas 153ms; `quant.technical_engine` 202ms (with pandas_ta_classic). End-to-end initialize 0.74-0.84s.
- Impact: Medium. It only delays "ready" (header, first submit), not first paint, but a user who types fast waits ~1s before `run.start` is even accepted. Every `/resume`-driven respawn after a crash pays it again.
- Fix: (a) lazy-import `report_view` inside `_report_for` (server.py:349); import `app.events.models` stays (needed). (b) Make `build_report_view`'s `EvidenceFact`/`_format_fact_value` import lazy or move them to a light module. (c) Lazy-import `pandas_ta_classic` in `quant.technical_engine` (the 200ms). (d) Run `initialize` response with minimal info first, build `FinAIRepl` in a background thread/task while the UI is already usable (session title can arrive as a notification). (e) Optionally `python -X importtime` regression test / `-X frozen_modules`, `PYTHONDONTWRITEBYTECODE` unset (keep .pyc).
- Risk: Low for (a)-(c); Medium for (d) (protocol/ordering change).

### #4 Reducer is O(n) per event: `seenSequences` Set copied on every event
- Where: `reducer.ts:77` (`new Set([...state.seenSequences, sequence])`), `reducer.ts:245` (`responseText` concat, fine), `reducer.ts:92-96,278-281` activity map rebuilds.
- Evidence: measured: 3000 `response.delta` events through `reduceEvent` = 167ms (about 55us/event average, growing linearly per event, so quadratic overall; a 10k-event run is ~1.5s of main-thread time spread over the run, blocking input/paint). Reasoned beyond that.
- Impact: Low-medium; main-thread stall grows with run length, and deltas are 64-char chunks (`model_streaming.py:221`), so a 20KB answer = ~300 events, small. Tool-heavy runs are the larger risk.
- Fix: track `latestSequence` + a small recent window, or mutate a Set held in the collector; ignore dupes by `sequence <= latestSequence` if the bridge guarantees ordering (it does, single writer).
- Risk: Low (pure function; existing reducer parity tests).

### #5 Unminified 1.1 MB bundle, no compile cache: ~0.3s cold start
- Where: `esbuild.config.mjs` (`minify:false`, `sourcemap:false`); `marked`, `ink`, `react`, `string-width`, `wrap-ansi`, `yoga` all parsed at startup.
- Evidence: measured: `node dist/cli.js --version` ~0.30s (0.31 user). Node baseline is ~0.04s, so ~0.25s is module parse/eval.
- Impact: Medium for first paint. Every launch pays it.
- Fix: enable `minify:true` (or at least `minifyWhitespace/minifySyntax`), call `module.enableCompileCache()` (Node >=22.1; engines says >=20, so guard it) at top of cli.tsx, and lazy-load rare paths (`SessionPicker`, `HelpPanel`, `commands/handlers`). Move `--help/--version` before heavy imports with dynamic `import()` for the App.
- Risk: Low; check minified output still passes snapshot tests (no function-name dependence).

### #6 `uv run` fallback and eager spawn when no `.venv`
- Where: `process.ts:84-92`. If `.venv/bin/python` is absent (fresh clone, or when launched via another venv), `uv run --project` re-resolves/syncs the env on every start (typically 0.2-1s+, and may start installs).
- Evidence: reasoned (not measured; `.venv` exists here). 
- Fix: prefer `FINAI_PYTHON`, then `.venv`, then `uv run --frozen --no-sync` to skip lock resolve; print a one-time "starting backend..." message.
- Risk: Low.

### #7 Minor protocol/IO items (no measured problem, noted for completeness)
- `NdjsonWriter` flushes per event and `FdWriter` uses blocking `os.write` on the asyncio loop (`__main__.py:23-28`, `framing.py:140`): if the Node side stalls (e.g. busy re-rendering, #2), the pipe (64KB) fills and the Python event loop, including cancellation handling, blocks. Reasoned. Fix: asyncio write transport / `connect_write_pipe` or coalesce deltas (batch `response.delta` events in 30-50ms windows on the Python side).
- Each 64-char delta carries full pydantic `display` + event meta; coalescing 64-char deltas into ~256-512 chars reduces JSON parse + reducer + notify count 4-8x. `JSON.parse` of per-line messages is not a bottleneck (messages are small; 8 MiB line cap in framing.ts:11 never approached except possibly `report`).
- `LineReader.push` always copies (`Buffer.from(chunk)` framing.ts:68, `#append` copy line 113): trivial for current sizes.
- `ClippedTail.tsx:160-164` has an effect without deps (measures after every render, may trigger a second render per frame when height changes). Add `[children]`-independent guard or measure in layout only when `liveText` length changed.
- `liveActivities` (App.tsx:~132) rebuilds the activities map on every render (spread of all activities) while running; memoize on `state`.

## 3. Quick wins vs larger refactors

Quick wins (hours, low risk)
1. Move spinner/elapsed ticking into `LiveActivity` so `App` stops re-rendering at 10Hz; `React.memo` Composer, StatusLine, StreamingAnswer (#2).
2. Lazy `report_view` import + lazy `pandas_ta_classic` (about 0.3-0.4s off ready time) (#3).
3. Minify bundle, `module.enableCompileCache()` (#5).
4. Replace `seenSequences` copy with an ordered-sequence check (#4).
5. Try Ink `incrementalRendering: true` (#2).
6. Fix docs/code drift on streaming commit (`docs/frontend.md:77`).
7. Coalesce `response.delta` into larger chunks on the Python side (#7).

Larger refactors
- Streaming/incremental results: progressive report sections and commit-complete-blocks (#1). Needs protocol + frontend + coordination with the backend review gate.
- Background `FinAIRepl` construction with early `initialize` (#3d).
- Non-blocking write transport on the Python side (#7).

## 4. UX improvements for perceived speed
- Show evidence the moment it exists: key figures, price/technical signals and sources as cards while the LLM is still writing (#1). Biggest single perceived-speed gain.
- Stage list with checkmarks and per-stage times (planning, data, analysis, writing) instead of only a single "current operation" line; the reducer already tracks stages (`reducer.ts:87-105`) but only the current one plus up to 3 tools is shown (`LiveActivity.tsx:18`).
- Show "Starting backend..." / ready indicator in the status line during the ~1s bootstrap, and a skeleton header at first paint (`StatusLine` currently has no bridge status; `status` is available from `useBridge`). Enter pressed before ready should show "queued, connecting..." not a silent wait.
- Elapsed is shown (`LiveActivity.tsx:40`) but there is no ETA or "N of M tools"; add counts (`3/5 data sources done`) from `activeTools` + completed activities.
- Cancel hint in the live region ("Esc to cancel") and a distinct "cancelling..." state (the phase exists: `cancelling`) with a timeout fallback.
- When the model is silent (review gate / structured output), say so: "Drafting report (answer appears when complete)" with time since model request, so a quiet 20-40s does not look hung. Emit `provider.stream.started` progress as "model responding".
- Reduce re-rendered chrome: keep the composer visible and stable (no flicker) while the live region updates; see #2.

## Files referenced
- /home/zeek/ML/financial-analyst-system/frontend/src/cli.tsx, src/ui/App.tsx, src/ui/hooks/useBridge.ts, src/ui/hooks/useElapsed.ts, src/ui/LiveActivity.tsx, src/ui/ClippedTail.tsx, src/ui/Answer.tsx, src/render/markdown.tsx, src/state/{store,reducer}.ts, src/bridge/{process,framing,client}.ts, esbuild.config.mjs
- /home/zeek/ML/financial-analyst-system/backend/finai/bridge/{__main__,server,framing}.py, backend/finai/report_view.py, backend/app/core/agent_loop/{runtime,model_streaming}.py (interaction points only)
