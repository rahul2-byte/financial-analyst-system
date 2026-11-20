# Runtime contract notes

Notes on the contract between the Python runtime (`backend/app/`, `backend/finai/`) and any presentation layer, in particular the Ink UI reached through the bridge (see [`../frontend.md`](../frontend.md)). Line numbers refer to the working tree at investigation time and may have drifted.

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
- Event JSON schemas are exported by `finai/bridge/schema.py` (`TypeAdapter(ResearchEvent)`) into `protocol/schema/`. Other `model_json_schema()` calls are for `LookupAnswerV1` and `ReportDraft` in `app/core/agent_loop/publication.py:710` and `runtime.py:297, 312`.
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
- Line-oriented REPL: `FinAIRepl.run()` (session.py:240) and `research()` (session.py:95). They print to stdout and serve non-TTY input.

### Bridge wiring

- `finai.bridge.__main__` builds a `FinAIRepl` and hands it to `BridgeServer` (`finai/bridge/server.py`). `run.start` sets `repl.mode` and spawns one task that iterates `repl.typed_stream(query)`, reduces each event with `reduce_event` and forwards it as a `run.event` notification. `run.finished` is sent once in `finally`.
- Session methods call `FinAIRepl.resume_session`, `new_session` and `compact_context`, plus `SessionStore.list_sessions`, `clear_pending` and the trace ledger.
- The runtime is pull-based: a client consumes an async event stream. It is not a callback model.

### Cancellation (Esc)

- The UI sends `run.cancel`; the bridge calls `task.cancel()` on the run task.
- Propagation: `CancelledError` is raised in the `async for`. In `_agent_loop_stream` (session.py:225-227) it sets `status="cancelled"` and re-raises. `finally` writes the run record with status `cancelled`. The bridge catches the error and sends `run.finished` with outcome `cancelled`.

### Timeouts

No timeout in the UI itself. Runtime timeouts come from `backend/app/config/models.py`:

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

- Intended flow: the UI would show the prompt and details, then either re-run with `"yes"` (approve) or call `clear_pending` (reject). The Ink UI has no approval screen because the runtime never emits the event.
- Persistence: `session.py:183-192` writes `pending.json` with `{"kind": "approval", run_id, query, prompt, details}`.
- **Problem:** on the next call, `_agent_loop_stream` (session.py:127-130) sees `kind == "approval"`, clears pending, and treats `"yes"` as a brand-new user query. `approved_tool_ids` is accepted by `ResearchRunner.stream` but the session never passes it. Since the runtime never emits `approval.requested`, this path is not reachable today. A UI should not rely on it without fixing the runtime first.

### Clarification (`clarification.requested`)

- The runtime emits `ClarificationRequested` and then `RunCompleted(terminal_status="awaiting_clarification")` (`session_runtime.py:920-961`, `runtime.py:437` and others). It also writes `checkpoint.json` via `checkpoint_writer` (session_runtime.py:952, runtime.py:427, 644, 1113, 1195, 1440).
- UI: the clarification prompt is shown as the end of the run, and the next user message is submitted as an ordinary query.
- Runtime side: `_agent_loop_stream` (session.py:131-136) resumes **only** if `pending.json` has `kind == "clarification"`. It then restores `history` from `checkpoint.json` and appends the user message. **Nothing writes `pending.json` with kind `clarification`** (only `session.py:184` writes pending, with kind approval). So that branch is dead. In practice the answer is appended to the stored transcript and run as a normal query. Whether the runtime's own checkpoint is used anywhere else was not traced.

## 4. Commands

Slash commands are implemented in the UI (`frontend/src/commands/`). The runtime is not involved except through bridge methods.

| command | behaviour | bridge method |
|---|---|---|
| `/help` | Show command list and key reference | (local) |
| `/clear` | Clear the conversation display | (local) |
| `/new` | Start a new conversation (session rotated) | `session.new` → `FinAIRepl.new_session()` |
| `/sources` | Show deduped sources from the last run | (local) |
| `/status` | Show phase and latest sequence | (local) |
| `/debug` | Show last events and bridge stderr | (local) |
| `/trace` | Show last 12 trace records and ledger path | `trace.tail` |
| `/artifact` | Show the last run's artifact path | (local) |
| `/logs` | Show `<data-dir>/sessions/<session>/runs/` | (local) |
| `/mode [guided\|review\|autonomous]` | Show or set the mode, sent with the next run | (local) |
| `/context` | Show token estimate and compaction limits | `context.info` → `ContextBudget` |
| `/compact` | Compact older messages now | `context.compact` → `FinAIRepl.compact_context()` |
| `/sessions` | Open the session picker | `session.list` → `SessionStore.list_sessions(root)` |
| `/resume <id-prefix>` | Resume a session by unique prefix | `session.resume` → `FinAIRepl.resume_session()` |
| `/history` | List prior user queries | `session.history` |
| `/retry` | Re-run the last user query | (local) |
| `/exit` | Exit | `shutdown` |

Unknown commands print "Unknown command /<name> — try /help" and are not sent to the runtime.

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

- `finai/__main__.py`: lazily imports `cli.main`. If a missing module is `pydantic`, `httpx` or `fastapi`, it prints a hint and exits with status 2.
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
  7. If stdin and stdout are TTYs and no query was given, `main` replaces the process with the Ink UI (`exec_ts_ui`, before any provider or tracing setup); otherwise `run_plain_terminal` (`FinAIRepl.run()`).
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

The UI also sets the phases `starting` (when a run is submitted), `cancelling` (on cancel) and `cancelled` (when the run ends cancelled) itself.

Terminal events: `run.completed`, `run.cancelled`, `run.failed`.

## 8. Display helpers with product logic (`backend/finai/display.py` and `plain.py`)

These rules live in Python. The bridge applies them and sends the results as the `display` object, so a client does not reproduce them:

| function | what it does |
|---|---|
| `VERBS` / `NOUNS` maps | verb map (fetch→Fetched, analyze→Analyzed...) and tool-to-noun map (`fetch_fundamentals`→"fundamentals", etc.) |
| `tool_name` | strips the `prefix:` from a label (`data:fetch_stock_data` → `fetch_stock_data`) |
| `noun` | short noun for failures and the collapsed summary |
| `tool_label` | raw tool id → human label (`Fetched stock data`, or `Fetching stock data` when active); never shows raw ids |
| `tool_detail` | drops JSON and `k=v` dumps; special-cases `key values:` for technical overview (`close ₹<x>`); max 40 chars |
| `failure_detail` | maps "no usable"/"unavailable" to "no usable articles" (news) or "no usable data"; strips raw ids with `RAW_ID` (`\b[a-z_]+:[a-z_]+\b`) |
| `short` | whitespace collapse and ellipsis truncation |
| `failed_nouns` | unique nouns of failed `tool:` activities |
| `QUOTE_SYMBOL` / `instrument_from_sources` | extracts `SYMBOL.NS` or `.BO` from `/quote/...` source URLs |
| `has_tool_trail` | any `tool:` activity exists (controls whether the trail is shown; chat-only runs produce none) |
| `dedupe_sources` / `source_label` | numbered, deduped sources; host shown only when it differs from the title |
| `CANDIDATE`, `ACRONYMS`, `title_name`, `parse_clarification` | clarification candidate parsing (`- SYM (EX) Name` or `- Name (SYM, EX)`) and name title-casing with an acronym whitelist |
| `build_display` | assembles the per-event `Display` payload from the helpers above |

Also in `backend/finai/display.py` (shared with `state.py` and `plain.py`):

| name | what it does |
|---|---|
| `REVIEW_UNAVAILABLE_NOTE` | text shown when output review is unavailable |
| `PYDANTIC_VALUE_ERROR` | regex that strips pydantic validation dumps |
| `friendly_error` | reduces a validation dump to one sentence |
| `provider_notice` | builds "⚠ OpenRouter error (<reason>): <label> — <message>" from `provider.failed`; uses `REASON_LABELS` |
| `review_unavailable` | true when `output_review == "unavailable"` on the event or its meta |
| `PROVIDER_LABELS` / `DATASET_LABELS` | labels used by `source_label`, which falls back to "Source (no title provided)" |

Also used: `sanitize_terminal_text` (`finai/safety.py`). The UI applies the equivalent (`frontend/src/render/sanitize.ts`) to any text from the runtime.

## Gaps and risks

1. The approval flow is inconsistent: resuming sends `"yes"` as a new query, and the runtime never emits the events. Define the contract before building a UI for it.
2. The clarification resume branch (`kind == "clarification"`) is never written. Confirm the intended resume semantics first.
3. Event and protocol schemas are exported from the Pydantic models (`python -m finai.bridge.schema`); keep them in step with `app/events/models.py`.
4. There is no session delete API.
5. `CheckStageResult`, `ContextCompacted`, `SkillSelected` and `RouteDecisionMade` are emitted but have no UI reducer branch; decide whether the TS UI should show them.
6. Event sequence can be out of order. Dedupe by `sequence` and apply out-of-order events, as `reduce_event` does.
