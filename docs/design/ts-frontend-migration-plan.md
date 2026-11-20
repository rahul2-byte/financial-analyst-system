# TS frontend migration plan (option 3)

Status: **plan only, nothing is implemented yet**. Branch base: `feat/tui-redesign`.
Contract source of truth: [`ts-frontend-contract-notes.md`](ts-frontend-contract-notes.md). Line numbers below come from that file. Re-check them before editing, because they drift.
Visual source of truth: [`tui-redesign.md`](tui-redesign.md) (tokens, layout, show/hide rules).

## 0. Goal and non-goals

**Goal.** Replace the Textual interactive UI with a TypeScript terminal UI (Ink + React) that runs as the parent process, Claude Code style. The Python runtime stays as is and runs as a child process behind a small JSON-RPC bridge. The user-visible behaviour must match the current Textual TUI, then improve on it: native scrollback, smoother streaming, and faster input.

**Non-goals (do not do these):**
- Do not port any runtime, provider, quant, routing, or prompt code to TS. Financial logic stays in Python (AGENTS.md).
- Do not change `--plain`, `--json`, one-shot query mode, or the non-TTY REPL. Those stay pure Python.
- Do not add an HTTP or SSE server. FastAPI stays root/health only.
- Do not implement the approval flow. It is dormant in the runtime (contract notes §3).
- Do not delete Textual code until phase P7 is signed off by the user.
- Do not change event models in `backend/app/events/models.py`. The bridge only reads them.

## 1. Architecture

```
terminal (TTY)
   │  keys / ANSI
   ▼
node frontend/dist/cli.js            ← parent process, owns the terminal (Ink, raw mode)
   │  spawn, stdio pipes
   │  stdin  : JSON-RPC requests        (NDJSON, UTF-8)
   │  stdout : JSON-RPC responses+notifs (NDJSON, UTF-8)
   │  stderr : Python logs → ring buffer + .finai/logs/bridge.stderr.log
   ▼
python -m finai.bridge               ← child process, no terminal access
   └─ FinAIRepl.typed_stream(query) → ResearchEvent → +display → notification
```

Key rules:
1. **One process owns the terminal**: the Node process. Python never writes to the TTY.
2. **The Python stdout fd is protocol only.** At bridge start, `os.dup(1)` becomes the protocol writer and `os.dup2(2, 1)` sends stray `print()` calls to stderr.
3. **Product wording stays in Python.** The bridge adds a `display` object to each event with labels, cleaned details, friendly errors, source labels and clarification candidates, computed by the existing Python helpers. TS renders these strings and does not re-derive them.
4. **Structural state lives in TS.** The TS reducer ports `reduce_event` (state.py) over raw and display data. Golden tests make it match Python exactly.
5. **There is one active run at a time.** Prompts submitted during a run are queued in TS, as Textual does today.

### Entry points

| command | behaviour |
|---|---|
| `python -m finai` (TTY, no query, no `--plain/--json`) | unchanged (Textual) until P7 |
| `python -m finai --ui ts` | `os.execvp` into `node frontend/dist/cli.js` with the same args (P6) |
| `frontend/bin/finai` (node) | TS UI. If not a TTY, or if `--plain`, `--json` or a positional query is given, exec `python -m finai` with the same args |
| `python -m finai.bridge [--data-dir ...] [--session ID] [--replay-snapshots P] [--fake-events P] [--fake-delay-ms N]` | the bridge server, never run by humans directly |

## 2. Wire protocol v1

### 2.1 Framing

- UTF-8 NDJSON: one JSON object per line, terminated with `\n`. Never pretty-print. Escape embedded newlines with JSON escaping.
- Max line length is 8 MiB. A reader that exceeds it drops the line and logs a `-32700` error.
- Both sides must tolerate unknown fields (forward compatibility). The TS side ignores unknown event `type`s and logs them to the debug buffer.
- Writer: Python serializes with `json.dumps(obj, ensure_ascii=False, separators=(",", ":"))` under an `asyncio.Lock` and flushes after each line.
- Reader: Python uses `asyncio.StreamReader` on stdin (`loop.connect_read_pipe`, limit 8 MiB). TS uses `readline` over `child.stdout` with `crlfDelay: Infinity`.

### 2.2 Envelope

JSON-RPC 2.0. Requests have `id` (integer, from TS) and get exactly one response. Notifications have no `id`.

### 2.3 Methods (TS → Python)

| method | params | result | errors |
|---|---|---|---|
| `initialize` | `{protocol_version: 1, client: {name, version}, terminal: {columns, rows}}` | `{protocol_version: 1, server_version, session: SessionInfo, mode, data_dir, model: {id, fallback_id}?}` | -32004 |
| `run.start` | `{client_run_id: string(uuid4), query: string, mode: "guided"\|"review"\|"autonomous"}` | `{accepted: true}` | -32001, -32602 |
| `run.cancel` | `{client_run_id}` | `{cancelled: bool}` (false if already finished) | -32002 |
| `session.new` | `{}` | `{session: SessionInfo}` | -32001 |
| `session.resume` | `{id_prefix: string}` | `{session: SessionInfo}` | -32001, -32003 |
| `session.list` | `{limit?: int = 50}` | `{sessions: SessionSummary[]}` | |
| `session.history` | `{}` | `{queries: string[]}` (user messages, oldest first) | |
| `context.info` | `{}` | output of `ContextBudget` used by `/context` (`app_commands.context_text` inputs), as a dict | |
| `context.compact` | `{}` | `FinAIRepl.compact_context()` dict | -32001 |
| `trace.tail` | `{limit?: int = 12}` | `{records: object[], ledger_path: string}` | |
| `shutdown` | `{}` | `{}`, then the server exits 0 after flushing | |

- `SessionInfo = {id, title, message_count, run_count}`
- `SessionSummary` = the `SessionStore.list_sessions` dict (contract notes §5)

### 2.4 Notifications (Python → TS)

| method | params |
|---|---|
| `run.event` | `{client_run_id, event: ResearchEvent (model_dump(mode="json")), display: Display \| null}` |
| `run.finished` | `{client_run_id, outcome: "completed"\|"failed"\|"cancelled"\|"clarification"\|"error", run_id: uuid\|null, artifact_path: string\|null, message: string\|null}` |
| `bridge.log` | `{level: "debug"\|"info"\|"warning"\|"error", message}`, sent only when `--debug` |

`run.finished` is **always** sent exactly once per accepted `run.start`, after the last `run.event`. That includes cancellation (the runtime raises `CancelledError`, the bridge catches it and sends `outcome: "cancelled"`) and unexpected exceptions (`outcome: "error"`, message = `friendly_error(str(exc))`, traceback to stderr only).

### 2.5 Error codes

| code | meaning |
|---|---|
| -32700 / -32600 / -32601 / -32602 / -32603 | JSON-RPC standard |
| -32001 | `RunInProgress`: a run is active, so the session or run method is refused |
| -32002 | `NoActiveRun`: unknown or finished `client_run_id` |
| -32003 | `SessionNotFound`: no match or an ambiguous prefix. `data: {matches: [...]}` |
| -32004 | `ProtocolMismatch`: `data: {server: 1, client: N}` |

### 2.6 `Display` object (bridge enrichment)

All strings pass through `sanitize_terminal_text` before they are sent. The fields are optional and only present for the event types listed.

| event type | display fields | Python source |
|---|---|---|
| `tool.started/completed/failed/progress` | `label` (e.g. "Fetched stock data"), `noun`, `detail` (≤40 chars, cleaned), `failure_detail` (failed only) | `_tool_label`, `_noun`, `_tool_detail`, `_failure_detail` (render.py:155-234) |
| `stage.*` | `label`, `detail` | event fields, sanitized |
| `provider.failed` | `notice` (may be null), `friendly` | `provider_notice`, `friendly_error` (plain.py:74-103) |
| `provider.retrying` | `detail` ("<reason> · <delay>s") | state.py:164 logic |
| `provider.stream.started` | `detail` ("first byte X.Xs") | state.py:176 logic |
| `provider.completed` | `detail` ("N attempt(s) · Xs") | state.py:187 logic |
| `tool.failed`, `run.failed`, `stage.failed` | `friendly` | `friendly_error` |
| `sources.updated` | `sources: [{label, url, host \| null}]` (host only when it differs from the label) | `source_label`, `render_sources` rules |
| `clarification.requested` | `candidates: [{symbol, name, exchange}]`, `lines: string[]` (non-candidate lines) | `_CANDIDATE`, `_title_name` (render.py:420-440) |
| `run.completed` | `review_unavailable: bool`, `review_note: string\|null`, `instrument: string\|null`, `failed_nouns: string[]` | `review_unavailable`, `instrument_from_sources`, `_failed_nouns` over a per-run Python `PresentationState` the bridge keeps |

P2a must **refactor these helpers into one pure module** (`backend/finai/display.py`) that both `render.py` and the bridge import. Do not duplicate them in Python. `render.py` keeps thin wrappers so the Textual UI still works.

### 2.7 Example exchange

```jsonl
→ {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocol_version":1,"client":{"name":"finai-tui","version":"0.1.0"},"terminal":{"columns":120,"rows":40}}}
← {"jsonrpc":"2.0","id":1,"result":{"protocol_version":1,"server_version":"0.1.0","session":{"id":"a1b2","title":"New research session","message_count":0,"run_count":0},"mode":"guided","data_dir":".finai"}}
→ {"jsonrpc":"2.0","id":2,"method":"run.start","params":{"client_run_id":"6f1e…","query":"HDFC Bank fundamentals","mode":"guided"}}
← {"jsonrpc":"2.0","id":2,"result":{"accepted":true}}
← {"jsonrpc":"2.0","method":"run.event","params":{"client_run_id":"6f1e…","event":{"type":"run.started","meta":{…,"sequence":1},"query":"HDFC Bank fundamentals"},"display":null}}
← {"jsonrpc":"2.0","method":"run.event","params":{"client_run_id":"6f1e…","event":{"type":"tool.started","meta":{…},"tool":"data:fetch_fundamentals","tool_id":"t1","detail":null},"display":{"label":"Fetching fundamentals","noun":"fundamentals","detail":null}}}
← {"jsonrpc":"2.0","method":"run.finished","params":{"client_run_id":"6f1e…","outcome":"completed","run_id":"…","artifact_path":".finai/sessions/a1b2/runs/….json","message":null}}
```

### 2.8 Versioning

- `PROTOCOL_VERSION = 1` lives in `backend/finai/bridge/protocol.py` and `frontend/src/protocol/version.ts`. A test asserts they are equal.
- Additive changes (new optional fields, new event types or methods) keep v1. Removing or renaming a field bumps the version.
- On a mismatch, TS shows: `Frontend and backend are out of sync. Run: uv sync && npm --prefix frontend run build`.

## 3. Schema and type generation

1. `backend/finai/bridge/schema.py`, with the function `export_schemas(out_dir: Path) -> list[Path]`. It writes:
   - `protocol/schema/research_event.schema.json`, from `TypeAdapter(ResearchEvent).json_schema(mode="serialization")`
   - `protocol/schema/protocol.schema.json`: every Pydantic model in `bridge/protocol.py` (params, results, notifications, `Display`, `SessionInfo`)
2. CLI: `PYTHONPATH=backend uv run python -m finai.bridge.schema --out protocol/schema`.
3. `frontend/scripts/gen-types.mjs` runs `json-schema-to-typescript` over both files and writes `frontend/src/protocol/generated.ts`, with a "do not edit" header.
4. **The generated files are committed.** A Python test checks that the schema JSON is up to date (regenerate to tmp, compare). A TS test does the same for `generated.ts` (`npm run gen:types:check`).
5. Discriminator: `ResearchEvent` must come out as a TS union discriminated on `type`. If the generator emits loose types, `frontend/src/protocol/events.ts` adds a hand-written `type`→interface map over the generated interfaces. Do not hand-write the field shapes.

## 4. Bridge server (Python)

Package `backend/finai/bridge/`:

| file | responsibility |
|---|---|
| `__init__.py` | exports `PROTOCOL_VERSION` |
| `__main__.py` | arg parsing (§1 table), stdout fd swap, logging to stderr and `<data-dir>/logs/finai.log`, `asyncio.run(serve(...))`; ignore SIGINT (`signal.signal(SIGINT, SIG_IGN)`), exit cleanly on SIGTERM |
| `framing.py` | `NdjsonReader` and `NdjsonWriter` (lock, flush, 8 MiB limit) |
| `protocol.py` | Pydantic v2 models for every method's params and result, both notifications, `Display`, error codes, `PROTOCOL_VERSION` |
| `server.py` | `BridgeServer`: dispatch table, one `asyncio.Task` per run, cancel, session methods, `shutdown` |
| `fake.py` | `FakeRepl`: replays a fixture event list (`backend/tests/fixtures/hdfc_run_events.json` format) with `--fake-delay-ms` between events and honours cancel. Used by dev, tests and screenshots, with no API keys |
| `schema.py` | §3 |

And `backend/finai/display.py`: the pure helpers from §2.6, moved out of `render.py` and `plain.py`, plus `build_display(event, run_state) -> Display | None`.

Server rules:
- Construct `FinAIRepl(data_dir, session, replay_snapshots)` exactly as `cli.main` does (cli.py:248-289), so tracing and validation behave the same. Do the heavy import **after** writing nothing. `initialize` waits on construction, which takes about 0.94 s.
- `run.start`: refuse if a run is active (-32001). Set `repl.mode = params.mode`. Spawn a task that does `async for event in repl.typed_stream(query)`, keeps a per-run `PresentationState` via `reduce_event`, and sends `run.event`. In `finally`, send `run.finished`. Map the outcome from the terminal event: `run.completed` with `terminal_status == "awaiting_clarification"` → `clarification`.
- `run.cancel` calls `task.cancel()`. That reproduces the Esc path (contract notes §2, "Cancellation").
- Session methods call the same `FinAIRepl` and `SessionStore` APIs that `cli.build_app` callbacks use (contract notes §2, "TUI wiring", and §5).
- stdin EOF means the parent died: cancel any run, wait at most 2 s for the `finally` persistence, exit 0.
- Never log event payloads at info level. Traces are sensitive (AGENTS.md).

## 5. TS frontend

### 5.1 Stack (pin exact versions at install; record them in `frontend/package.json`)

| purpose | package |
|---|---|
| UI | `ink@6`, `react@19` |
| input | `ink-text-input` is **not** used. Write the composer in-house (multi-line, history, completion) |
| markdown | `marked` (lexer only), with a custom Ink renderer |
| width | `string-width`, `wrap-ansi` (already Ink dependencies; pin them to match) |
| bundle | `esbuild`, giving a single `dist/cli.js` with a `#!/usr/bin/env node` banner |
| types | `typescript`, `@types/react`, `@types/node` |
| tests | `vitest`, `ink-testing-library` |
| codegen | `json-schema-to-typescript` |
| screenshots | `@xterm/headless`, `@xterm/addon-serialize` (dev only) |

Use npm with a committed `package-lock.json`. The engines field is `node >=20`. ESM only (`"type": "module"`). `tsconfig` has `strict: true` and `noUncheckedIndexedAccess: true`.

### 5.2 Layout

```
frontend/
  package.json  package-lock.json  tsconfig.json  vitest.config.ts  esbuild.config.mjs
  bin/finai                      # node shim → dist/cli.js (or exec python for non-TTY/one-shot)
  scripts/gen-types.mjs
  scripts/snapshot.tsx           # §8 screenshots
  src/
    cli.tsx                      # arg parse, TTY check, render(<App/>), exit codes
    protocol/{generated.ts, events.ts, version.ts}
    bridge/
      framing.ts                 # NDJSON line reader/writer
      client.ts                  # BridgeClient: request(), on(notification), pending map, timeouts
      process.ts                 # locate python, spawn, stderr ring buffer, restart, shutdown
      fake.ts                    # in-memory FakeBridge for unit tests
    state/
      types.ts                   # PresentationState, ActivityState, Phase (mirror of state.py)
      reducer.ts                 # reduceEvent(state, event, display) – pure
      transcript.ts              # TranscriptItem union + commit rules (what goes to <Static>)
      store.ts                   # external store + throttled subscribe (≤30 fps)
    commands/{registry.ts, handlers.ts}
    render/{theme.ts, sanitize.ts, markdown.tsx, format.ts}
    ui/
      App.tsx
      Header.tsx  UserMessage.tsx  ActivityTrail.tsx  LiveActivity.tsx
      Answer.tsx  StreamingAnswer.tsx  Sources.tsx  Clarification.tsx
      Notice.tsx  RunFooter.tsx  CommandOutput.tsx
      Composer.tsx  Completion.tsx  StatusLine.tsx  SessionPicker.tsx  HelpPanel.tsx
      hooks/{useKeybindings.ts, useBridge.ts, useElapsed.ts}
  test/
    goldens/*.json               # generated by Python (§6)
    reducer.golden.test.ts  framing.test.ts  client.test.ts  markdown.test.ts
    composer.test.tsx  app.fake.test.tsx  e2e.bridge.test.ts
```

### 5.3 Rendering model (Claude Code style)

- **Scrollback** is the terminal's own. Everything finished goes into Ink `<Static items={transcript}>` and is never re-rendered, so native scroll, copy and search work.
- **Live region** (re-rendered) holds only `LiveActivity`, the `StreamingAnswer` tail, `Completion`, `Composer` and `StatusLine`. Cap its height at `rows - 2`.
- **Streaming commit.** While `response.delta` events arrive, `transcript.ts` splits the text into a stable prefix (complete Markdown blocks: separated by a blank line and not inside an open code fence or table) and a tail. Stable blocks are appended to `<Static>` as `answer-chunk` items, and only the tail stays live. On `run.finished`, the remainder is committed. This removes flicker on long answers.
- **Commit order per run:** `user` → `activity-trail` (committed collapsed when the run finishes, or when the first answer chunk commits) → `answer-chunk`* → `sources` → `clarification` | `notice` → `run-footer`.
- **Store.** The reducer runs on every event. The React re-render is throttled to 33 ms with `useSyncExternalStore` over `store.ts`. Keystrokes bypass the throttle.
- **Resize.** Static content does not reflow, which is the same as Claude Code. The live region reflows. `Ctrl+L` clears the screen and re-prints the transcript at the new width.

### 5.4 Components → spec

| component | content | rules (from `tui-redesign.md`) |
|---|---|---|
| `Header` | `FIN-AI`, then session title, mode, model in dim | printed once into Static at start and after `/new` and `/clear` |
| `UserMessage` | `› query` | paper bold on graphite, full width |
| `LiveActivity` | spinner + `current_operation` + elapsed + up to 3 active tool labels | hides `model` and completed `provider` activities, like `render_activity` |
| `ActivityTrail` | committed: `Gathered evidence · N tools` + failed nouns; expanded with `Ctrl+O` | no raw tool ids; chat-only runs render nothing (`has_tool_trail`) |
| `Answer` / `StreamingAnswer` | Markdown | headings in ledger, tables boxed with the rule colour, code in graphite; numbers keep gain/loss colours only when the Markdown already marks them, so no inference |
| `Sources` | numbered `display.sources` | host dim, only when it differs from the label |
| `Clarification` | aligned `SYMBOL  Name · EX` + passthrough lines | `display.candidates` |
| `Notice` | warn, loss or dim one-liners (provider notice, review unavailable, cancelled, errors) | prefix glyphs `⚠`, `✕`, `·` |
| `RunFooter` | `✓ 12.4s · 6 tools · partial evidence` | partial status lives here, not in the answer |
| `Composer` | `›` prompt, multi-line, placeholder `Ask about a stock, or / for commands` | rule-coloured top border only |
| `Completion` | slash command list under the composer | max 8 rows, highlight in ledger |
| `StatusLine` | left: session title, mode. Right: `esc cancel · ctrl+o details · /help` while running, otherwise context tokens | dim, one line |
| `SessionPicker` | replaces the composer: filterable list, ↑/↓, Enter resumes, Esc closes | |
| `HelpPanel` | inline command and key list, committed to Static as `CommandOutput` | |

`theme.ts` holds the tokens from `tui-redesign.md` (ink, graphite, rule, paper, dim, ledger, gain, loss, warn) as hex. Use truecolor when `chalk.level >= 3`, otherwise map to the nearest 256 colour. Honour `NO_COLOR`.

`sanitize.ts` ports `sanitize_terminal_text` (safety.py, 13 lines). It is applied to every raw runtime string the TS side renders (response text, query echo, error messages). `markdown.tsx` also ports `render_response`'s sanitization (render.py:415). Both are covered by goldens.

### 5.5 Keybindings

| key | idle | running | picker open |
|---|---|---|---|
| Enter | submit (command or run) | queue prompt (shows `queued` line) | resume selected |
| Shift+Enter / Ctrl+J / `\`+Enter | newline | newline | – |
| Esc | close completion, else no-op | `run.cancel` → phase cancelling | close picker |
| Ctrl+C | clear the composer; on an empty composer, a second press within 1.5 s exits | cancel the run (like Esc) | close picker |
| Ctrl+D | exit if the composer is empty | – | – |
| ↑ / ↓ | history (when the cursor is on the first or last line), or the completion selection | same | move selection |
| Tab | accept completion | accept completion | – |
| Ctrl+O | toggle expanded activity details | same | – |
| Ctrl+L | clear the screen and re-print the transcript | same | – |
| Ctrl+A / Ctrl+E / Ctrl+W / Ctrl+U / Alt+←/→ | readline editing | same | – |

Shift+Enter works only where the terminal sends a distinct sequence (kitty or CSI-u). Ctrl+J is the documented fallback.

### 5.6 Commands

| command | handler | via |
|---|---|---|
| `/help` | `HelpPanel` from the registry | local |
| `/clear` | clear the screen and transcript, reset state, re-print the header | local |
| `/new` | `session.new`, then clear the screen and transcript | RPC |
| `/sources` | re-print the last run's sources | local |
| `/status` | phase, latest sequence, session id, bridge pid, protocol version | local |
| `/debug` | last 20 events (type and sequence) + bridge stderr tail (40 lines) | local |
| `/trace` | `trace.tail` → formatted like `app_commands.trace_text` | RPC |
| `/artifact` | the last `run.finished.artifact_path` | local |
| `/logs` | `Run artifacts: <data_dir>/sessions/<id>/runs/` | local |
| `/mode [m]` | show or set the mode; sent with the next `run.start` | local |
| `/context` | `context.info` → formatted like `context_text` | RPC |
| `/compact` | `context.compact` → result line | RPC |
| `/sessions` | `session.list` → `SessionPicker` | RPC |
| `/resume <prefix>` | `session.resume`; on -32003 with matches, list them | RPC |
| `/history` | `session.history` | RPC |
| `/retry` | re-submit the last query | local |
| `/exit` | graceful shutdown (§7) | local |
| unknown | `Unknown command /x — try /help` | local |

Session and compact commands are refused while a run is active, with the notice `Finish or cancel the current run first`.

## 6. Reducer port and golden parity

1. P2b writes the script `scripts/gen_reducer_goldens.py`. For each fixture in `backend/tests/fixtures/` (HDFC run) plus synthetic streams that cover every handled branch, it writes `frontend/test/goldens/<name>.json`:
   ```json
   {"events":[{"event":{...},"display":{...}}], "snapshots":[{"after_sequence":3,"state":{...}}], "final":{...}}
   ```
   The state is Python `PresentationState` serialized with sorted keys: UUID → str, frozenset → sorted list, enum → value.
2. Synthetic streams are required for:
   - out-of-order and duplicate sequences
   - a provider retry and then failure (notice path)
   - a tool failure with a pydantic dump in the message
   - two `sources.updated` with overlap
   - clarification
   - a cancelled run
   - a failed run
   - `run.completed` with `output_review: "unavailable"`
   - a chat-only run with no tools
   - a sanitize case with ESC and control chars
3. `reducer.golden.test.ts` replays each file and deep-equals every snapshot and the final state.
4. A Python test checks that the goldens are fresh, so changing `state.py` without regenerating them fails CI.
5. The UI-set phases (`starting`, `cancelling`, `cancelled`) are TS actions (`localPhase(state, phase)`), tested separately.

## 7. Process lifecycle (`bridge/process.ts`)

- **Python discovery** in this order:
  1. `$FINAI_PYTHON`
  2. `<repo>/.venv/bin/python`
  3. `uv run --project <repo> python`

  `<repo>` is resolved from `dist/cli.js` up to the directory containing `pyproject.toml`. Env adds `PYTHONPATH=<repo>/backend` and `PYTHONUNBUFFERED=1`. cwd is the user's cwd, because `--data-dir` is relative to it.
- **Start-up:** spawn the bridge **before** the first Ink render. Render the header and composer immediately, with the status line showing `starting…`. Typing is allowed; a submit before `initialize` resolves is queued.
- **stderr:** keep a ring buffer of the last 500 lines and append it to `<data-dir>/logs/bridge.stderr.log`. Never print it to the terminal except through `/debug` or a crash notice.
- **Crash** (unexpected exit):
  - Mark any active run `error`.
  - Show the notice `Backend stopped (exit N).` with the last 5 stderr lines.
  - Respawn once, automatically, at the next submit. If it crashes again within 10 s, stop and tell the user to run `/debug`.
- **Request timeouts:** 10 s for every method except `run.start` (5 s to accept) and `initialize` (30 s). `run.event`s have no timeout.
- **Exit** (`/exit`, Ctrl+D, or Ctrl+C twice): send `shutdown`; after 2 s SIGTERM; after a further 2 s SIGKILL. Restore the terminal (Ink `unmount`) **before** waiting.
- **Exit codes:** 0 normal, 1 bridge failed to start, 130 on SIGINT received outside raw mode.
- **Signals:** in raw mode Ctrl+C is a key, not a signal. The bridge ignores SIGINT anyway. Cancellation goes only through RPC.

## 8. Screenshots and visual checks

`frontend/scripts/snapshot.tsx --scenario <name> --cols 120 --rows 40 --out <file.ansi>`:
- Renders `<App>` against `FakeBridge`, or the real bridge with `--fake-events`.
- Writes all Ink stdout bytes into `@xterm/headless`, drives the scenario keystrokes, waits for idle, then serializes the visible buffer **plus scrollback** to ANSI with `@xterm/addon-serialize`.

`scripts/ts_tui_screenshot.py <file.ansi> <out.png>` converts that ANSI with Rich `Text.from_ansi`, then `Console(record=True, width=cols).export_svg()`, then `rsvg-convert` to PNG. This is the same pipeline as `scripts/tui_screenshot.py`.

Scenarios (all required for P7): `idle`, `running` (mid-tools), `streaming`, `completed-hdfc`, `clarification`, `provider-error`, `cancelled`, `session-picker`, `help`, `narrow-80col`.
Output goes to `docs/design/screenshots/ts-<scenario>.png`. Compare it side by side with the existing Textual PNGs.

## 9. Phases and tasks

**Rules for every task:**
- Sonnet, `effort: medium`, `subagent_type: general-purpose`.
- Edit only the files the task owns.
- Parallel tasks use `isolation: "worktree"`. When running in a worktree, use the main checkout's `.venv` binaries if `uv run --offline` fails (known pymupdf cache issue), and the absolute Node path `/home/zeek/.nvm/versions/node/v26.10.0/bin/{node,npm,npx}` (the zsh nvm wrapper recurses).
- Do not run `npm install` until decision D1 is approved.
- Long commands run in the background with a log.
- Report format: files changed, commands run with real output tails, and anything unverified.

**Global done gate** (every Python task):
```
uv run --offline ruff check backend evals && uv run --offline mypy backend && uv run --offline pytest backend/tests --no-cov -q
```

**Global done gate** (every TS task, run in `frontend/`):
```
npm run typecheck && npm test -- --run && npm run build
```

### P0: Checkpoint (main session)
- Get decisions D1–D4 from the user (§12).
- Make one checkpoint commit on `feat/ts-frontend`, branched from `feat/tui-redesign`.

### P1: Protocol models and schema (1 agent, Python)
- **Owns:**
  - `backend/finai/bridge/{__init__,protocol,schema}.py`
  - `protocol/schema/*.json`
  - `backend/tests/test_bridge_protocol.py`
- **Do:**
  - §2.3–2.6 as Pydantic models
  - §3 steps 1, 2 and 4 (Python half)
  - round-trip tests for every model
  - a test that the schema JSON is fresh
  - a test that `ResearchEvent` is in the schema with all 27 `type` constants
- **Done when:**
  - the global Python gate passes
  - `PYTHONPATH=backend uv run --offline python -m finai.bridge.schema --out protocol/schema && git diff --exit-code protocol/schema`

### P2a: Display module (1 agent, Python), parallel with P2b after P1
- **Owns:**
  - `backend/finai/display.py`
  - `backend/finai/render.py` and `backend/finai/plain.py`, only to replace the moved helpers with imports or wrappers
  - `backend/tests/test_display.py`
- **Do:** §2.6. Move the helpers without changing behaviour. Add `build_display`.
- **Done when:** the global Python gate passes. All existing rendering tests are unchanged and green (`test_terminal_rendering.py`, `test_phase0_ux.py`, `test_answer_quality.py`).

### P2b: Bridge server and fake mode (1 agent, Python)
- **Depends on:** P1. It imports `build_display` from P2a. Until then, stub `display=None` behind a single function `_display(event, state)`, then wire it in after P2a merges.
- **Owns:**
  - `backend/finai/bridge/{__main__,framing,server,fake}.py`
  - `backend/tests/test_bridge_server.py`
  - `scripts/gen_reducer_goldens.py`
  - `frontend/test/goldens/*.json`
- **Do:**
  - §4
  - §6 steps 1, 2 and 4
  - tests that drive `BridgeServer` over in-memory streams: initialize, run → events → finished, cancel mid-run → `cancelled`, a second `run.start` during a run → -32001, an unknown method → -32601, a malformed line → -32700 and the server keeps going, stdin EOF → clean exit
  - a subprocess test: spawn `python -m finai.bridge --fake-events …` and assert that stdout contains only valid JSON-RPC lines
- **Done when:**
  - the global Python gate passes
  - `printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocol_version":1,"client":{"name":"t","version":"0"},"terminal":{"columns":80,"rows":24}}}' '{"jsonrpc":"2.0","id":2,"method":"shutdown","params":{}}' | PYTHONPATH=backend uv run --offline python -m finai.bridge --fake-events backend/tests/fixtures/hdfc_run_events.json --data-dir "$(mktemp -d)"` prints two result lines and exits 0

### P3: TS scaffold, protocol client and process (1 agent, TS)
- **Depends on:** P1 (schema) and D1. It may run in parallel with P2a and P2b.
- **Owns:**
  - everything in `frontend/` except `src/state`, `src/ui`, `src/commands`, `src/render` and `test/goldens`
- **Do:**
  - `package.json` scripts: `build`, `typecheck`, `test`, `gen:types`, `gen:types:check`, `snapshot`
  - esbuild config
  - §3 step 3
  - `framing.ts`, `client.ts`, `process.ts`, `fake.ts`
  - tests:
    - framing: split chunks, multi-byte UTF-8 across chunk boundaries, oversize lines
    - client: request/response matching, error mapping, timeout, notification fan-out
    - process: spawn the fake bridge, initialize, shutdown, kill escalation
- **Done when:** the global TS gate passes, and `npm run gen:types:check` passes.

### P4: Reducer and transcript model (1 agent, TS)
- **Depends on:** P2b goldens and P3.
- **Owns:** `frontend/src/state/*`, `frontend/src/render/sanitize.ts`, `frontend/test/reducer.golden.test.ts`, `frontend/test/transcript.test.ts`
- **Do:**
  - §6 step 3
  - `transcript.ts` commit rules (§5.3), including stable-prefix splitting. Unit-test fences, tables and lists that are split across deltas.
  - throttled `store.ts`
- **Done when:** the global TS gate passes, and every golden matches.

### P5a: Transcript UI (1 agent, TS, worktree), parallel with P5b
- **Depends on:** P4.
- **Owns:**
  - `frontend/src/render/{theme,markdown,format}.ts(x)`
  - `frontend/src/ui/{Header,UserMessage,ActivityTrail,LiveActivity,Answer,StreamingAnswer,Sources,Clarification,Notice,RunFooter,CommandOutput}.tsx`
  - their tests
- **Do:** the components from §5.4 as pure props → Ink trees, and the Markdown renderer (headings, paragraphs, bold and italic, inline code, code blocks, lists, tables, blockquotes, links shown as `text (host)`).
- **Done when:** the global TS gate passes, and the ink-testing-library frame tests pass for each component at 80 and 120 columns.

### P5b: Input UI and commands (1 agent, TS, worktree)
- **Depends on:** P4.
- **Owns:**
  - `frontend/src/ui/{Composer,Completion,StatusLine,SessionPicker,HelpPanel}.tsx`
  - `frontend/src/ui/hooks/useKeybindings.ts`
  - `frontend/src/commands/*`
  - their tests
- **Do:** §5.5 and §5.6. The composer supports multi-line input, history, readline keys, paste of multiple lines as one input (bracketed paste) and completion.
- **Done when:** the global TS gate passes, and the key-sequence tests pass for every row of §5.5.

### P6: App wiring, launcher, screenshots, e2e (1 agent, TS + small Python)
- **Depends on:** P2a, P2b, P5a and P5b merged.
- **Owns:**
  - `frontend/src/{cli.tsx, ui/App.tsx, ui/hooks/{useBridge,useElapsed}.ts}`
  - `frontend/bin/finai`
  - `frontend/scripts/snapshot.tsx`
  - `scripts/ts_tui_screenshot.py`
  - `backend/finai/cli.py`, only the `--ui {textual,ts}` flag and the exec
  - `frontend/test/{app.fake.test.tsx, e2e.bridge.test.ts}`
  - `docs/design/screenshots/ts-*.png`
- **Do:**
  - wire the store, bridge and transcript together
  - queued prompts
  - the §7 lifecycle
  - §8
  - `e2e.bridge.test.ts` spawns the real Python bridge in fake mode, submits the HDFC query and asserts the final transcript text (answer, sources and footer)
- **Done when:**
  - the global TS gate passes
  - the global Python gate passes
  - `npm --prefix frontend run snapshot -- --all` writes all 10 PNGs
  - `PYTHONPATH=backend uv run --offline python -m finai --ui ts --help` exits 0

### P7: Parity review and cutover (main session + 1 Haiku agent for the checklist)
- A Haiku agent walks the §10 checklist using screenshots and fake-mode runs, and reports pass or fail per row with evidence paths.
- The main session reviews the diffs and screenshots. The user runs one live session with real keys.
- **Cutover**, only on user approval and in a separate commit: make `--ui ts` the default in `cli.py`, keep `--ui textual` for one release, and document both in the README.
- **Textual removal** is a later, separate PR (D3).

### Parallelism map

```
P0 → P1 ─┬─ P2a ───────────┐
         ├─ P2b ──┐        │
         └─ P3 ───┴─ P4 ─┬─ P5a ─┬─ P6 → P7
                         └─ P5b ─┘
```

There are never more than 3 agents at once (P2a, P2b and P3), which is within the limit of 4.

## 10. Parity checklist (P7)

| # | behaviour | how it is verified |
|---|---|---|
| 1 | The HDFC fixture renders an answer, sources (deduped and numbered) and a footer with elapsed time | `completed-hdfc` screenshot + e2e |
| 2 | No raw tool ids (`data:fetch_…`) appear anywhere | grep the snapshot ANSI for `_RAW_ID` |
| 3 | A chat-only run shows no evidence trail | synthetic golden + snapshot |
| 4 | Esc cancels and shows `· Cancelled`; the run record status is `cancelled` | e2e + `.finai` run JSON |
| 5 | A provider failure shows the one-line notice, not a stack trace | `provider-error` |
| 6 | Clarification candidates are aligned, and the next message starts a normal run | `clarification` + e2e |
| 7 | All 17 commands behave as in §5.6 | P5b tests + a manual run |
| 8 | `/sessions` and `/resume` switch sessions; `/new` rotates the id | e2e |
| 9 | Queued prompts run in order after the current run | app.fake test |
| 10 | 80-column layout has no broken wrapping | `narrow-80col` |
| 11 | `NO_COLOR=1` renders legibly | snapshot with env |
| 12 | `--plain`, `--json` and one-shot output are byte-identical to before | existing tests + a diff on the fixture |
| 13 | A bridge crash produces a notice, the next submit respawns it, and the terminal is restored on exit | process test + manual |
| 14 | The §11 budgets are met | measured numbers in the P7 report |

## 11. Performance budgets

| metric | budget | how it is measured |
|---|---|---|
| first paint (header and composer) | ≤ 200 ms | `FINAI_TIMING=1` logs `performance.now()` at the first Ink render |
| backend ready (`initialize` resolved) | ≤ 1.5 s warm | the same log |
| keypress → echo | ≤ 16 ms p95 | composer test with a fake clock + a manual check |
| streaming CPU (Node) | ≤ 25 % of one core at 200 deltas/s | fake bridge `--fake-delay-ms 5`, `/usr/bin/time` |
| Node RSS after a 50-run session | ≤ 200 MB | `process.memoryUsage()` in `/status` |
| `dist/cli.js` size | ≤ 3 MB | `ls -l` |

## 12. Decisions needed from the user

| id | decision | recommendation |
|---|---|---|
| D1 | Allow `npm install` of the §5.1 packages in `frontend/`. It is small (no native builds) and creates `node_modules` and `package-lock.json` | yes |
| D2 | Node becomes a runtime requirement for the interactive UI (`node >=20`). Python-only users keep `--ui textual` and plain mode | yes |
| D3 | When to delete Textual: after P7 plus one release, in a separate PR | after one release |
| D4 | The user enables the daily `--ui ts` default only after their own live session | yes |

## 13. Risks and mitigations

| risk | mitigation |
|---|---|
| Stray Python prints corrupt the protocol | fd swap (§1 rule 2) + a subprocess test that every stdout line parses |
| TS and Python wording drift | wording comes only from `display` (Python); goldens guard the reducer; freshness tests guard the schemas |
| Ink flicker on long answers | streaming commit to `<Static>`, live region capped, 30 fps throttle |
| Static output doesn't reflow on resize | accepted (same as Claude Code); `Ctrl+L` re-prints |
| Shift+Enter is not detectable | Ctrl+J and `\`+Enter fallbacks, shown in `/help` |
| 0.94 s Python import delays the first answer | spawn before render; input works immediately; submissions queue until ready |
| Dormant approval and dead clarification-resume paths | out of scope; an `approval.requested` renders a warn notice `Approval is not supported in this UI` and nothing else |
| Two toolchains in CI | the TS gate is a separate job; the Python gate is unchanged |
| Sensitive traces in logs | the bridge logs no payloads at info level; `bridge.stderr.log` lives under `.finai/` (gitignored) |

## 14. Delegation prompt template

Every task prompt the main session sends must contain:

```
Objective: <phase id + one sentence>
Read first: docs/design/ts-frontend-migration-plan.md §<sections>, docs/design/ts-frontend-contract-notes.md §<sections>
Files you own (edit only these): <list>
Do not touch: everything else; never edit backend/app/**, prompts, or other phases' files
Interfaces fixed by the plan: <§ refs>; if the plan is wrong, stop and report, do not improvise
Environment: Node via /home/zeek/.nvm/versions/node/v26.10.0/bin/*; uv --offline; no new packages beyond §5.1; tools missing or denied → stop and report
Definition of done: <exact commands>
Budget: <N tool calls>; report ≤ 300 words
Report: files changed, commands run + real output tail, unverified items
```

## 15. Task tracker

Update this table as work proceeds, so the work can resume after a restart.

| task | status | agent | worktree/branch | output / evidence |
|---|---|---|---|---|
| P0 checkpoint + decisions | todo | main | feat/ts-frontend | |
| P1 protocol + schema | todo | sonnet | – | |
| P2a display module | todo | sonnet | worktree | |
| P2b bridge server + fake + goldens | todo | sonnet | worktree | |
| P3 TS scaffold + client + process | todo | sonnet | worktree | |
| P4 reducer + transcript | todo | sonnet | – | |
| P5a transcript UI | todo | sonnet | worktree | |
| P5b input UI + commands | todo | sonnet | worktree | |
| P6 wiring + launcher + screenshots + e2e | todo | sonnet | – | |
| P7 parity review + cutover | todo | main + haiku | – | |
