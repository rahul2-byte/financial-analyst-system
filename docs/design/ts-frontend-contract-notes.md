# TS frontend contract notes

Read-only investigation of the contract between the Textual UI (`backend/finai/`) and the Python runtime (`backend/app/`). Branch `feat/tui-redesign`. Line numbers refer to the working tree at investigation time.

## 1. Events (`backend/app/events/models.py`)

### Shared meta

`EventMeta` (models.py:12-19, frozen):

| field | type |
|---|---|
| `event_id` | UUID |
| `run_id` | UUID |
| `conversation_id` | UUID |
| `sequence` | int, >= 1 (per-run monotonic, assigned by `EventFactory`) |
| `occurred_at` | datetime (UTC, ISO 8601 when serialised) |

Every event is `{"type": "<literal>", "meta": EventMeta, ...payload}`. `EventFactory` (models.py:305-326) assigns `event_id`, `sequence` and `occurred_at`.

### Event classes

`type` is a `Literal` default on each class. Fields are listed after `meta`.

| line | class | `type` | fields |
|---|---|---|---|
| 22 | RunStarted | `run.started` | query: str |
| 28 | RunCompleted | `run.completed` | terminal_status: str; duration_ms: float?; artifact_path: str?; evidence_status: str?; evidence_availability: list[dict[str, object]] = []; completion_reason: str?; output_review: str? ("unavailable" / "not_configured" / null); route_reason_codes: list[str] = [] |
| 44 | RunFailed | `run.failed` | message: str; category: str = "internal" |
| 51 | RunCancelled | `run.cancelled` | reason: str = "cancelled by user" |
| 57 | StageStarted | `stage.started` | stage: str; label: str |
| 64 | StageCompleted | `stage.completed` | stage: str; label: str; detail: str? |
| 72 | StageFailed | `stage.failed` | stage: str; label: str; message: str |
| 80 | CheckStageResult | `check.stage` | stage: str; label: str; passed: bool; attempt: int >= 0; max_attempts: int >= 0; retrying: bool = false; reasons: list[str] = [] |
| 99 | ToolStarted | `tool.started` | tool: str; tool_id: str?; detail: str? |
| 107 | ToolCompleted | `tool.completed` | tool: str; tool_id: str?; detail: str?; duration_ms: float? |
| 116 | ToolFailed | `tool.failed` | tool: str; tool_id: str?; message: str |
| 124 | TextDelta | `response.delta` | text: str |
| 130 | ModelRequestStarted | `model.request.started` | model: str; round: int |
| 137 | ModelResponseCompleted | `model.response.completed` | round: int; has_tool_calls: bool = false |
| 144 | ProviderAttemptStarted | `provider.attempt.started` | provider: str = "openrouter"; attempt: int |
| 151 | ProviderRetrying | `provider.retrying` | provider: str; attempt: int; status_code: int?; delay_ms: float; reason: str |
| 161 | ProviderStreamStarted | `provider.stream.started` | provider: str; attempt: int; first_byte_ms: float |
| 169 | TokenUsage (payload, not an event) | - | prompt_tokens: int?; completion_tokens: int?; total_tokens: int?; verified: bool = false |
| 176 | ProviderCompleted | `provider.completed` | provider: str; attempts: int; duration_ms: float; first_token_ms: float?; model_id: str?; usage: TokenUsage? |
| 187 | ProviderFailed | `provider.failed` | provider: str; attempts: int; phase: str; message: str; status_code: int?; duration_ms: float?; timeout: bool?; partial_output: bool?; model_id: str?; usage: TokenUsage?; reason: str? (quota / auth / rate_limit / timeout / server_error / error) |
| 204 | ToolProgress | `tool.progress` | tool: str; tool_id: str; message: str |
| 212 | ContextCompacted | `context.compacted` | compacted_messages: int; estimated_tokens: int |
| 219 | SkillSelected | `skill.selected` | skill_id: str; version: str; package_hash: str |
| 227 | SourcesUpdated | `sources.updated` | sources: list[dict[str, str]] |
| 233 | ApprovalRequested | `approval.requested` | prompt: str; details: str? |
| 240 | ApprovalResolved | `approval.resolved` | decision: "approved" / "rejected" / "revised" |
| 246 | ClarificationRequested | `clarification.requested` | prompt: str |
| 252 | RouteDecisionMade | `route.decision.made` | intent: str; execution_mode: str; model_tier: str; confidence: float in [0,1]; reason_codes: list[str]; required_tools: list[str]; reason: str = ""; selected_provider: str?; selected_model: str?; next_action: str?; prompt_injection_risk: str = "low"; risk_flags: list[str]; evidence_sufficient: bool?; escalation_reason: str? |

Notes:
- `ApprovalRequested` and `ApprovalResolved` are defined and handled by the UI but are **never emitted** by the runtime (`grep factory.make(ApprovalRequested` in `backend/app` returns nothing). The approval path is dormant. Only `approved_tool_ids` plumbing exists (`app/core/agent_loop/runtime.py:227-278`).
- `ClarificationRequested` is emitted from `runtime.py:437, 655, 1125, 1207, 1451` and `session_runtime.py:960`.
- `ToolProgress.tool_id` is `str` (required), while `ToolStarted/Completed/Failed.tool_id` is `str | None`.
- `CheckStageResult` is in the union but no UI reducer branch exists for it in `state.py` (it falls through to `return state`).

### Union and schema

- `ResearchEvent` (models.py:271-300) is `Annotated[A | B | ..., Field(discriminator="type")]`. It has **27 members** (`RouteDecisionMade` last). Pydantic v2 discriminated union. There is no named `TypeAdapter` in the events module.
- **No JSON schema export** for events. The only `model_json_schema()` calls are for `LookupAnswerV1` and `ReportDraft` in `app/core/agent_loop/publication.py:710` and `runtime.py:297, 312`.
- Serialisation: `event.model_dump(mode="json")`. The ledger (`app/events/ledger.py:37-66`) wraps it as:
  `{schema_version: 1, event_id, run_id, conversation_id, sequence, occurred_at, event_type, payload, artifact_refs: []}`, with `payload` = the event minus `meta` and `type`. Payloads over 16,384 bytes are spilled to an artifact (`{stored_as_artifact: true}` plus `artifact_refs`). Values are passed through `_redact`.
- `app/events/__init__.py` re-exports the classes.

## 2. Starting a run

### Python side

- `ResearchRunner.stream` is an **async generator** (`finai/session_runtime.py:87-96`):
  `stream(history: list[Message], query: str, conversation_id: UUID, *, mocked_tools=None, approved_tool_ids: set[str]|None=None, checkpoint_writer: Callable[[dict], None]|None=None, message_writer: Callable[[Message], None]|None=None) -> AsyncIterator[ResearchEvent]`
- `FinAIRepl` (`finai/session.py:27`) is the facade. Key methods:
  - `typed_stream(query) -> AsyncIterator[ResearchEvent]` (session.py:120), which delegates to `_agent_loop_stream` (session.py:125-238).
  - `_agent_loop_stream` loads or resumes the pending state, appends the user message, calls `runtime.stream(...)`, and yields each event. It persists the trace (`store.append_trace_event`), `begin_run` on `run.started`, `write_pending` on `approval.requested`, and `write_run` in `finally`. On `run.completed` it rewrites `artifact_path` to `.finai/sessions/<id>/runs/<run_id>.json`.
- Plain-mode REPL: `FinAIRepl.run()` (session.py:240) and `research()` (session.py:95). They print to stdout. These are not used by the TUI.

### TUI wiring

- `cli.build_app(repl)` (`finai/cli.py:209-236`) creates `FinAIApp(session_store=repl.store, compact_callback=repl.compact_context, mode=repl.mode)`. It sets `app.event_stream = stream` (cli.py:230-235), where `stream(query)` is an async generator that sets `repl.mode = app.mode` and then `async for event in repl.typed_stream(query): yield event`.
- Callbacks set on the app (cli.py:225-228):
  - `session_callback(session_id: str) -> None`
  - `new_session_callback() -> None`
  - `clear_pending_callback() -> None` (`repl.store.clear_pending()`)
  - `compact_callback() -> dict[str, int|str]`
- `FinAIApp.__init__` is at `finai/app.py:98-135`. The parameter is `event_stream: Callable[[str], AsyncIterator[ResearchEvent]]`.
- Starting a run: `on_composer_submitted` (app.py:283-320) → `_start_run(query)` (`finai/app_dispatch.py:41-56`). This creates `asyncio.create_task(self._consume(self.event_stream(query), activity_widget))` and stores it in `self._run_task`.
- `_consume` (app_dispatch.py:58-126) is an `async for` over the iterator. It calls `reduce_event` for each event, then renders. On exception it mounts an error and does not rethrow. In `finally` it posts `RunFinished(task)`. Queued prompts (`self._queued_prompts`) run after `RunFinished` (app_dispatch.py: `on_run_finished`, app.py:437-441).
- The UI is **not** a callback model. It is pull-based, so the TS side must consume an event stream.

### Cancellation (Esc)

- `BINDINGS` in app.py:82-96 map `escape` → `cancel_run` and `ctrl+c` → `cancel_or_exit`. `ctrl+z` → `quit_app`.
- `action_cancel_run` (app_dispatch.py:153-162) sets `PresentationPhase.CANCELLING` and calls `self._run_task.cancel()`.
- Propagation: `CancelledError` is raised in the `async for`. In `_agent_loop_stream` (session.py:225-227) it sets `status="cancelled"` and re-raises. `finally` writes the run record with status `cancelled`. In `_consume` (app_dispatch.py:93-113) it sets the phase to `CANCELLED`, mounts "· Cancelled", and does not rethrow.
- Esc is also bound in modals (`ApprovalScreen` reject, `SessionScreen` close, `HelpScreen` close). Those bindings take precedence when a modal is open.

### Timeouts

No timeout in the TUI itself. Runtime timeouts come from `backend/app/config/models.py`:

| line | setting | value (s) |
|---|---|---|
| 22 | FINAI_ROUTER_TIMEOUT_SECONDS | 10 |
| 33 | OPENROUTER_TIMEOUT | 600 |
| 34 | OPENROUTER_CONNECT_TIMEOUT | 5 |
| 35 | OPENROUTER_POOL_TIMEOUT | 2 |
| 36 | OPENROUTER_WRITE_TIMEOUT | 10 |
| 37 | OPENROUTER_READ_TIMEOUT | 60 |
| 42 | OPENROUTER_CIRCUIT_RECOVERY_TIMEOUT | 30 |
| 47 | OPENROUTER_REPAIR_TIMEOUT | 120 |
| 58 | YFINANCE_INFO_TIMEOUT_SECONDS | 15 |
| 67-68 | TINYFISH_SEARCH_TIMEOUT / QUERY | 45 / 8 |
| 73-74 | NEWS_PIPELINE_TOTAL_TIMEOUT / NEWS_EXTRACTION_TIMEOUT | 60 / 8 |
| 80 | UPSTOX_TIMEOUT | 20 |

Enforcement sites: `app/core/agent_loop/model_streaming.py:200` (`asyncio.wait_for` on each stream chunk) and `tool_execution.py:97` (`asyncio.timeout(timeout)` per tool).

## 3. Interactive requests

### Approval (`approval.requested`)

- Intended flow (UI side, all live in app):
  1. `_consume` sees `approval.requested` (app_dispatch.py:77-82) and pushes `ApprovalScreen(prompt, details)` with callback `_approval_result(bool|None)`. The screen dismisses with `True` (y/approve) or `False` (n/escape/reject) (`finai/screens.py:13-61`).
  2. `_approval_result(True)` (app_dispatch.py:128-142) appends a trace record and calls `_start_run("yes")`. `False` calls `_reject_pending()` (app_dispatch.py:144-151), which calls `clear_pending_callback()`.
  3. The composer also accepts text while `phase == WAITING_FOR_APPROVAL` (app.py:300-320): `d`/`details` (opens debug), `n`/`reject`/`cancel`, `y`/`approve`/`proceed`.
- Persistence: `session.py:183-192` writes `pending.json` with `{"kind": "approval", run_id, query, prompt, details}`.
- **Problem:** on the next call, `_agent_loop_stream` (session.py:127-130) sees `kind == "approval"`, clears pending, and treats `"yes"` as a brand-new user query. `approved_tool_ids` is accepted by `ResearchRunner.stream` but the session never passes it. Since the runtime never emits `approval.requested`, this path is not reachable today. Any TS port should not rely on it without fixing the runtime first.

### Clarification (`clarification.requested`)

- The runtime emits `ClarificationRequested` and then `RunCompleted(terminal_status="awaiting_clarification")` (`session_runtime.py:920-961`, `runtime.py:437` and others). It also writes `checkpoint.json` via `checkpoint_writer` (session_runtime.py:952, runtime.py:427, 644, 1113, 1195, 1440).
- UI: `_consume` sets `self._clarified = True` and mounts `render_clarification(prompt)` (app_dispatch.py:83-90). `_finish_run` returns early when `_clarified` is true (app_dispatch.py: `_finish_run`).
- Routing of the next user message: `on_composer_submitted` (app.py:283-320). If the phase is `WAITING_FOR_CLARIFICATION`, the text goes to `_mount_user(query)` and `_start_run(query)`. Ordinary messages behave the same way, so routing is identical.
- Runtime side: `_agent_loop_stream` (session.py:131-136) resumes **only** if `pending.json` has `kind == "clarification"`. It then restores `history` from `checkpoint.json` and appends the user message. **Nothing writes `pending.json` with kind `clarification`** (only `session.py:184` writes pending, with kind approval). So that branch is dead. In practice the answer is appended to the stored transcript and run as a normal query. Whether the runtime's own checkpoint is used anywhere else was not traced.

## 4. Commands

Registry: `finai/commands.py:15-61`, `CommandRegistry.default()`. Dispatch: `finai/app_dispatch.py:132-245` (`_command`). Parsing: `commands.parse_command` (commands.py:70-78, shlex). Output formatting: `finai/app_commands.py`.

| command | behaviour | Python function called |
|---|---|---|
| `/help` | Show command list and the help screen text | `CommandRegistry.help_text()` |
| `/clear` | Clear the conversation display only; resets UI state | (UI only) |
| `/new` | Start a new conversation (display cleared, session rotated) | `app.new_session_callback` → `build_app.new_session` → `FinAIRepl.new_session()` |
| `/sources` | Show deduped sources from the last run | `render.render_sources` |
| `/status` | Show phase and latest sequence | `app_commands.status_text` |
| `/debug` | Show last event and error log | `render.render_debug` |
| `/trace` | Show last 12 trace records and ledger path | `SessionStore.trace.read()` then `app_commands.trace_text` |
| `/artifact` | Show the last run's artifact path | (UI state `_last_artifact`) |
| `/logs` | Print the static text "Run artifacts: .finai/sessions/<session>/runs/" | (static text) |
| `/mode [guided\|review\|autonomous]` | Show or set the mode | (UI state; `repl.mode` updated on next run) |
| `/context` | Show token estimate and compaction limits | `ContextBudget.compact()` + `app_commands.context_text` |
| `/compact` | Compact older messages now | `FinAIRepl.compact_context()` (via `compact_callback`) |
| `/sessions` | Open the session picker modal | `SessionStore.list_sessions(root)` + `SessionScreen` |
| `/resume <id-prefix>` | Resume a session by unique prefix | `session_callback` → `FinAIRepl.resume_session()` |
| `/history` | List prior user queries | `app_commands.queries_text` |
| `/retry` | Re-run the last user query | `_start_run` (UI) |
| `/exit` | Exit | `App.exit()` |

Unknown commands print "Unknown command /<name> — try /help". Commands are not sent to the runtime. Composer completion uses `CommandRegistry.suggestion_items` (app.py `on_key` 357-375).

## 5. Sessions

### Files (under `--data-dir`, default `.finai/`)

Per session `root/sessions/<session_id>/` (`finai/session_store.py`):

| file | writer | content |
|---|---|---|
| `transcript.jsonl` | `SessionStore.append_message` (session_store.py:51) | one JSON line per message: `{"kind": "message", "message": Message, "created_at": ISO}`. `Message` = `{role: user\|assistant\|system\|tool, content, name?, tool_call_id?, tool_calls?}` (`app/models/request_models.py:8`). |
| `events.v1.jsonl` | `TraceLedger` (`app/events/ledger.py:28-66`) | append-only trace, one ledger record per event (format in section 1). |
| `events.jsonl` | `append_events` (session_store.py:61) | run events, written at `write_run` |
| `runs/<run_id>.json` | `write_run` (session_store.py:77-102) | `{run_id, session_id, query, status, created_at, events: [...], feedback: summarize_run(events)}`. `begin_run` writes status `running` first. |
| `pending.json` | `write_pending` (session_store.py:189) | `{kind: "approval", run_id, query, prompt, details}`. `kind: "clarification"` is read but never written. |
| `checkpoint.json` | `write_checkpoint` (session_store.py:192) | runtime checkpoint (messages etc.) |
| `context.json` | `write_context` (session_store.py:182) | compaction metadata |

Other: `root/logs/finai.log` (cli.py `main`, `--debug`), and a provider archive under `root` (`ProviderArchive(self.root)`, session.py:43).

### API

- `SessionStore(root, session_id)` (session_store.py:20-28). `session_id` must match `[A-Za-z0-9_-]{1,128}`.
- `FinAIRepl` (session.py): `__init__(root=None, session_id=None, replay_snapshots=None)`, `resume_session(id)` (session.py:63), `new_session()` (session.py:69, uuid4 hex), `compact_context()` (session.py:72).
- `SessionStore.list_sessions(root) -> list[dict[str, str]]` (session_store.py:255-306, static). Each dict has `id, title` (first line of the first user message, max 72 chars, else "New research session"), `message_count`, `run_count`, `last_status`, `last_activity`. Sorted by id descending.
- `SessionStore.load_history()` (session_store.py:38) and `SessionPersistence.load_history()`.
- `SessionStore.mark_incomplete_runs_interrupted()` (session_store.py:209) runs on every `FinAIRepl` start (session.py:59-61).
- **Delete:** no session delete API. The store only unlinks `pending.json` and `checkpoint.json` (session_store.py:203, 251).

## 6. Startup (`python -m finai`)

- `finai/__main__.py`: lazily imports `cli.main`. If a missing module is `pydantic`, `textual`, `httpx` or `fastapi`, it prints a hint and exits with status 2.
- `cli.parse_arguments` (cli.py:45-81):
  - `--data-dir PATH` (default `.finai`)
  - `--session ID`
  - `--replay-snapshots PATH` (JSON mapping, max 256 KB; disables live providers)
  - `--plain` (one-shot readable output)
  - `--json` (one-shot JSONL events)
  - `--debug` (diagnostics to `.finai/logs/finai.log`)
  - `--debug-payloads` (sets `FINAI_DIAGNOSTICS=payloads`)
  - `--mode {guided,review,autonomous}` (default guided)
  - positional `query...` (one-shot run)
- `main()` (cli.py:248-289):
  1. `initialize_tracing` (stdout suppressed)
  2. `_validate_cli_paths`
  3. logging to `<data-dir>/logs/finai.log`
  4. optional replay JSON
  5. `FinAIRepl(args.data_dir, args.session, replay_snapshots)`
  6. If a positional query is given → `run_one_shot` (exit code per `EXIT_CODE_HELP`, cli.py:90-103)
  7. If stdin and stdout are TTYs → `run_interactive` (Textual `FinAIApp.run_async`, cli.py:239-245); otherwise `run_plain_terminal` (`FinAIRepl.run()`, cli.py:201-206).
- Exit codes: 0 ok, 1 failed/denied/cancelled, 2 clarification, 3 degraded evidence, 130 Ctrl+C.
- Model selection and env: loaded by `app.config.settings` (imported at session_runtime.py:14). Not traced in detail. Config fields are in `backend/app/config/models.py`. `MissingOpenRouterKeyError` → exit 1.
- **Measured import cost:** `time PYTHONPATH=backend uv run --offline python -c "import finai.session_runtime"` → **0.94 s wall** (3.47 s user, 0.10 s sys, 379% CPU).

## 7. Presentation state (`backend/finai/state.py`)

`PresentationPhase` (state.py:44-57, StrEnum): `idle, starting, planning, researching, analysing, validating, generating, cancelling, waiting_for_approval, waiting_for_clarification, complete, failed, cancelled`.

`PresentationState` (state.py:67-85, frozen-style dataclass, reduced with `dataclasses.replace`):

| field | type | notes |
|---|---|---|
| `phase` | PresentationPhase | default idle |
| `run_id` | UUID? | set on `run.started` |
| `query` | str? | set on `run.started` |
| `response_text` | str | concatenation of `response.delta` |
| `response_delta_count` | int | |
| `terminal_status` | str? | from RunCompleted / RunFailed / RunCancelled |
| `error` | str? | RunFailed message |
| `latest_sequence` | int | max sequence seen |
| `last_event_type` | str? | |
| `current_operation` | str? | label of the running stage/tool/provider |
| `active_tools` | tuple[str, ...] | tool_ids currently running |
| `activities` | dict[str, ActivityState] | keys: stage name, `model`, `provider`, `output_review`, `tool:<tool_id>` |
| `sources` | list[dict[str, str]] | deduped accumulation |
| `seen_sequences` | frozenset[int] | duplicate guard (duplicates ignored; out-of-order applied) |

`ActivityState` (state.py:60-65): `label: str`, `status: "running"|"completed"|"failed"` (default running), `detail: str?`.

Reducer `reduce_event(state, event)` (state.py:104-316). Rules by event:

- Dedupe: if `sequence in seen_sequences`, return unchanged. Otherwise add it and set `latest_sequence = max(...)`, `last_event_type`.
- `run.started` (state.py ~120): phase `starting`, run_id, query.
- `stage.started` (127): marks the previous `current_operation` activity completed; sets `activities[stage]`; phase from stage name via `_phase_for_stage` (planning, research→researching, analysis→analysing, validation→validating, generation→generating; default researching); `current_operation = label`.
- `model.request.started` (144): phase generating; activity `model` "Contacting model".
- `provider.attempt.started` (153): activity `provider` "Contacting OpenRouter", detail "attempt N".
- `provider.retrying` (164): "Retrying OpenRouter", detail "<reason> · <delay>s".
- `provider.stream.started` (176): "Streaming response", detail "first byte X.Xs".
- `provider.completed` / `provider.failed` (187): activity `provider` completed (detail "N attempt(s) · Xs") or failed (detail = `friendly_error`; if `provider_notice` returns a line, the label becomes that line and detail is cleared). `current_operation = None`.
- `tool.progress` (202): updates `tool:<tool_id>` detail and sets `current_operation = message`.
- `stage.completed` / `stage.failed` (209): activity status completed or failed; detail = event.detail or event.message.
- `tool.started` (226): phase researching; `activities["tool:<tool_id or tool>"]`; appends to `active_tools`; `current_operation = tool`.
- `tool.completed` / `tool.failed` (237): status completed or failed; detail = `_short_detail(friendly_error(message) or detail)` (120 chars); removes from `active_tools`; clears `current_operation` if it equals the tool name.
- `response.delta` (264): phase generating; appends text; increments count.
- `sources.updated` (271): `sources = dedupe_sources([*sources, *event.sources])`.
- `approval.requested` (274): phase waiting_for_approval. `approval.resolved` (278): phase researching.
- `clarification.requested` (276): phase waiting_for_clarification.
- `run.completed` (280): running activities become completed; `output_review` activity added if `review_unavailable(event)` (`REVIEW_UNAVAILABLE_NOTE`); phase complete; `terminal_status`; clears `current_operation` and `active_tools`.
- `run.failed` (~299): phase failed, error = message, terminal_status failed.
- `run.cancelled` (~308): phase cancelled, terminal_status cancelled.
- Not handled (no branch, returns state unchanged, but sequence is still recorded): `check.stage`, `context.compacted`, `skill.selected`, `route.decision.made`, `model.response.completed`. (`provider.stream.started` and `tool.progress` are handled above.)

The UI also sets phases itself: `STARTING` in `_start_run` (app_dispatch.py:42), `CANCELLING` in `action_cancel_run` (app_dispatch.py:155), `CANCELLED` in `_consume` on cancel (app_dispatch.py:94).

Transition-driving events in `app_events.py`:
- `ACTIVITY_EVENTS` (app_events.py:5-26): skill.selected, model.request.started, provider.attempt.started, provider.retrying, provider.stream.started, provider.completed, provider.failed, tool.progress, context.compacted, stage.started/completed/failed, tool.started/completed/failed, run.completed/cancelled/failed.
- `TERMINAL_EVENTS` (app_events.py:27): run.completed, run.cancelled, run.failed.

## 8. Render helpers with product logic (`backend/finai/render.py` and `plain.py`)

Presentation-only functions are not listed. These contain rules a TS client must reproduce:

| function | line | what it does |
|---|---|---|
| `_VERBS` / `_NOUNS` maps | render.py:155, 168 | verb map (fetch→Fetched, analyze→Analyzed...) and tool-to-noun map (`fetch_fundamentals`→"fundamentals", etc.) |
| `_tool_name` | 179 | strips the `prefix:` from a label (`data:fetch_stock_data` → `fetch_stock_data`) |
| `_noun` | 183 | short noun for failures and the collapsed summary |
| `_tool_label` | 193 | raw tool id → human label (`Fetched stock data`); never shows raw ids |
| `_tool_detail` | 203 | drops JSON and `k=v` dumps; special-cases `key values:` for technical overview (`close ₹<x>`); max 40 chars |
| `_failure_detail` | 218 | maps "no usable"/"unavailable" to "no usable articles" (news) or "no usable data"; strips raw ids with `_RAW_ID` (render.py:176, `\b[a-z_]+:[a-z_]+\b`) |
| `_short` | 229 | whitespace collapse and ellipsis truncation |
| `_failed_nouns` | 234 | unique nouns of failed `tool:` activities |
| `_QUOTE_SYMBOL` / `instrument_from_sources` | 244, 247 | extracts `SYMBOL.NS` or `.BO` from `/quote/...` source URLs |
| `has_tool_trail` | 256 | any `tool:` activity exists (controls whether the trail is shown) |
| `render_activity` | 260 | the evidence trail: hides `model` and completed `provider`; "Gathered evidence · N tools"; collapsed summary; chat-only runs produce no trail |
| `render_sources` | 398 | numbered, deduped sources; host shown only when it differs from the title |
| `render_response` | 415 | sanitises response text before Markdown rendering |
| `_CANDIDATE`, `_ACRONYMS`, `_title_name` | 420, 424, 427 | clarification candidate parsing (`- SYM (EX) Name` or `- Name (SYM, EX)`) and name title-casing with an acronym whitelist |
| `render_clarification` | 440 | aligns candidates as `SYMBOL  Name · EX`; other lines pass through |
| `render_footer` | 493 | per-run footer with elapsed time |
| `render_debug` | 530 | last events and error details for `/debug` |

From `backend/finai/plain.py` (shared with state.py):

| function | line | what it does |
|---|---|---|
| `REVIEW_UNAVAILABLE_NOTE` | 35 | text shown when output review is unavailable |
| `_PYDANTIC_VALUE_ERROR` | 39 | regex that strips pydantic validation dumps |
| `dedupe_sources` | 42 | dedupe by `(url, source_label)` |
| `source_label` | ~55 | title, else `provider · dataset · instrument` derived from `/quote/<symbol>/<dataset>` paths; falls back to "Source (no title provided)". Uses `_PROVIDER_LABELS` and `_DATASET_LABELS` maps. |
| `friendly_error` | 74 | reduces a validation dump to one sentence |
| `provider_notice` | 87 | builds "⚠ OpenRouter error (<reason>): <label> — <message>" from `provider.failed`; uses `_REASON_LABELS` |
| `review_unavailable` | 103 | true when `output_review == "unavailable"` on the event or its meta |

Also used: `sanitize_terminal_text` (`finai/safety.py`, 13 lines). It must be reproduced on the TS side for any text from the runtime.

## Gaps and risks for a TS port

1. The approval flow is inconsistent: the UI resumes by sending `"yes"` as a new query, and the runtime never emits the events. Define the contract before porting.
2. The clarification resume branch (`kind == "clarification"`) is never written. Confirm the intended resume semantics first.
3. No JSON schema for events. A TS client needs a hand-written or generated schema from the Pydantic models (for example `ResearchEvent` via `TypeAdapter(ResearchEvent).json_schema()`, which is not wired up today).
4. There is no session delete API.
5. `CheckStageResult`, `ContextCompacted`, `SkillSelected` and `RouteDecisionMade` are emitted but have no UI reducer branch; decide whether the TS UI should show them.
6. Event sequence can be out of order. Dedupe by `sequence` and apply out-of-order events, as `reduce_event` does.
