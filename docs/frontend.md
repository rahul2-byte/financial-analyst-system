# Terminal UI

`python -m finai` (no query, attached to a TTY) replaces itself with `node frontend/dist/cli.js`, an Ink/React terminal UI. The UI owns the terminal and talks to a Python bridge child process over JSON-RPC. One-shot runs (`--plain`, `--json`, or a positional query) and non-TTY input stay in Python and never start Node.

## Build and test

```bash
cd frontend
npm install
npm run build          # dist/cli.js (bundle must stay under 3 MB)
npm run typecheck
npm test
npm run gen:types:check  # protocol/schema/*.json vs src/protocol/generated.ts
```

If node or `frontend/dist/cli.js` is missing, `python -m finai` prints `cd frontend && npm install && npm run build`. `frontend/bin/finai` launches the same bundle directly. Options: `--data-dir`, `--session`, `--mode guided|review|autonomous`, `--fake-events FILE`, `--fake-delay-ms N`.

## Processes

```
terminal ⇄ node frontend/dist/cli.js            (Ink, raw mode, owns the TTY)
              │ stdin/stdout: NDJSON JSON-RPC
              ▼
           python -m finai.bridge               (no terminal access)
              └─ FinAIRepl.typed_stream(query) → ResearchEvent → + display → notification
```

- The bridge duplicates fd 1 as the protocol writer and points `print()` at stderr, so stdout carries protocol only.
- Product wording (tool labels, friendly errors, source labels, clarification candidates) is computed in Python (`backend/finai/display.py`) and sent as a `display` object. The UI renders those strings and does not re-derive them.
- Structural run state lives in TS (`frontend/src/state/reducer.ts`), a port of `finai.state.reduce_event`. Golden files in `frontend/test/goldens/` (written by `scripts/gen_reducer_goldens.py`) keep both in step; a Python test fails when they are stale.
- One run is active at a time. Prompts typed during a run are queued.
- Python discovery: `$FINAI_PYTHON`, then `<repo>/.venv/bin/python`, then `uv run --project <repo> python`. `FINAI_BRIDGE_CMD` overrides the whole command. Bridge stderr is kept in a 500-line ring buffer and appended to `<data-dir>/logs/bridge.stderr.log`; `/debug` shows it.
- A bridge crash marks the active run `error`, shows the last stderr lines and respawns once at the next submit.
- Exit (`/exit`, Ctrl+D, Ctrl+C twice): `shutdown` RPC, SIGTERM after 2 s, SIGKILL after 2 s more. Ink restores the terminal first.

## Wire protocol (v1)

UTF-8 NDJSON, one JSON-RPC 2.0 object per line (max 8 MiB). Unknown fields are ignored. `PROTOCOL_VERSION` lives in `backend/finai/bridge/protocol.py` and `frontend/src/protocol/version.ts`; a test asserts they match. Additive changes keep v1.

| method (UI → bridge) | result |
|---|---|
| `initialize` `{protocol_version, client, terminal}` | `{protocol_version, server_version, session, mode, data_dir, model?}` |
| `run.start` `{client_run_id, query, mode}` | `{accepted}` |
| `run.cancel` `{client_run_id}` | `{cancelled}` |
| `session.new` / `session.resume {id_prefix}` / `session.list {limit?}` / `session.history` | session info, summaries or user queries |
| `context.info` / `context.compact` / `trace.tail {limit?}` | context budget, compaction result, trace records |
| `shutdown` | `{}`, then the bridge exits 0 |

| notification (bridge → UI) | params |
|---|---|
| `run.event` | `{client_run_id, event, display}`: `event` is a serialized `ResearchEvent` |
| `run.finished` | `{client_run_id, outcome, run_id, artifact_path, message}`: sent exactly once per accepted `run.start`; outcome is `completed`, `failed`, `cancelled`, `clarification` or `error` |
| `bridge.log` | `{level, message}`, only with `--debug` |

Errors: standard JSON-RPC codes plus `-32001` run in progress, `-32002` no active run, `-32003` session not found or ambiguous prefix (`data.matches`), `-32004` protocol mismatch. On mismatch the UI says to run `uv sync && npm --prefix frontend run build`.

Schemas are exported from the Pydantic models and committed: `PYTHONPATH=backend uv run python -m finai.bridge.schema --out protocol/schema`, then `npm run gen:types` writes `frontend/src/protocol/generated.ts`. Both are checked by tests.

## Bridge modules (`backend/finai/bridge/`)

`protocol.py` (models, error codes), `framing.py` (NDJSON reader/writer), `server.py` (`BridgeServer`: dispatch, one task per run, cancel, sessions), `schema.py` (schema export), `fake.py` and `fake_report.py` (replay a fixture event list with no API keys, used by tests and screenshots), `__main__.py` (arguments, fd swap, signals).

## Frontend layout (`frontend/src/`)

| directory | contents |
|---|---|
| `bridge/` | `client.ts` (JSON-RPC client, timeouts), `process.ts` (spawn, discovery, stderr buffer), `framing.ts`, `fake.ts` |
| `protocol/` | generated types, method surface, version |
| `state/` | `reducer.ts`, `store.ts` (33 ms throttled `useSyncExternalStore`), `transcript.ts` (what is committed and in which order) |
| `render/` | `markdown.tsx`, `format.ts`, `sanitize.ts`, `theme.ts` (colour tokens, 256-colour fallback) |
| `commands/` | slash-command registry and handlers |
| `ui/` | `App`, `Composer`, `Header`, `StatusLine`, `LiveActivity`, `ActivityTrail`, `StreamingAnswer`, `Answer`, `Sources`, `Clarification`, `RunFooter`, `Completion`, `SessionPicker`, `HelpPanel`, `report/` |

Rendering model:

- Finished transcript items go into Ink `<Static>` and are never re-rendered, so native scrollback, copy and search work. The live region holds only the running activity, the streaming tail, completion, composer and status line, capped at `rows - 2`.
- While `response.delta` events arrive, `transcript.ts` commits complete Markdown blocks (not inside an open code fence or table) and keeps only the tail live.
- Commit order per run: `user` → `activity-trail` → `answer-chunk`* → `sources` → `clarification` or `notice` → `run-footer`.
- Static content does not reflow on resize; `Ctrl+L` clears the screen and re-prints the transcript.
- All runtime text passes through `sanitize.ts` (ESC and control characters removed). Raw tool ids never reach the screen.

## Commands and keys

Commands: `/help /clear /new /sources /status /debug /trace /artifact /logs /mode /context /compact /sessions /resume /history /retry /exit`. Session and compact commands are refused while a run is active.

| key | effect |
|---|---|
| Enter / Shift+Enter, Ctrl+J, `\`+Enter | submit (queue while running) / newline |
| Esc | cancel the run, close completion or picker |
| Ctrl+C | cancel a run; clear the composer; twice on an empty composer exits |
| Ctrl+D | exit when the composer is empty |
| Tab, ↑/↓ | accept completion; history or completion selection |
| Ctrl+O | expand or collapse activity details |
| Ctrl+L | clear and re-print the transcript |

## Screenshots

`npm --prefix frontend run snapshot -- --all` (or `--scenario <name>`) renders the real `<App>` against a scripted bridge into a headless xterm, serializes the buffer to ANSI and runs `scripts/ts_tui_screenshot.py`, which converts it to SVG with Rich and to PNG with `rsvg-convert`. Output goes to `docs/design/screenshots/ts-<scenario>.png`. Scenarios: `idle`, `running`, `streaming`, `completed-hdfc`, `clarification`, `provider-error`, `cancelled`, `session-picker`, `help`, `narrow-80col`, `report-full`, `report-partial`, `report-80col`, `lookup`, `ctrl-o-last-run`. The harness fails on raw tool ids or lines wider than the terminal.

## Performance budgets

| metric | budget |
|---|---|
| first paint (header and composer) | ≤ 200 ms |
| backend ready (`initialize` resolved, warm) | ≤ 1.5 s |
| keypress to echo | ≤ 16 ms p95 |
| Node CPU while streaming 200 deltas/s | ≤ 25 % of one core |
| Node RSS after a 50-run session | ≤ 200 MB |
| `dist/cli.js` | ≤ 3 MB |

Related design notes: [`design/ts-frontend-contract-notes.md`](design/ts-frontend-contract-notes.md) (runtime event, session and state contract) and [`design/ts-report-ux-plan.md`](design/ts-report-ux-plan.md) (report presentation).
