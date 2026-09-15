# FIN-AI Modularization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make FIN-AI easier for a human engineer to navigate by separating CLI startup, session persistence, TUI presentation, model/tool execution, legacy graph compatibility, and deterministic financial logic while preserving observable behavior.

**Architecture:** Keep the existing Python packages and two runtime contracts, but make the boundary explicit: `finai` owns terminal interaction and session artifacts; `app.core.agent_loop` owns the production model/tool loop; `app.core.graph` and `PipelineOrchestrator` remain a compatibility runtime until consumers are measured; `agents`, `data`, and `quant` remain responsible for research and deterministic calculations. Refactor through small adapters and pure helpers rather than introducing generic Clean Architecture layers.

**Tech Stack:** Python 3.11+, Textual, Rich, FastAPI, LangGraph, Pydantic v2, asyncio, pytest, Ruff, mypy.

**Spec:** `docs/refactoring-plan.md`, `AGENTS.md`, and the monochrome TUI requirements from the preceding design requests.

## Global Constraints

- Preserve CLI commands, HTTP SSE event names, session files, trace files, approval behavior, cancellation, and quant outputs.
- LLMs must not perform financial calculations; all numeric logic remains in `backend/quant/` and deterministic data-processing modules.
- Do not remove the graph/orchestrator compatibility path until import and runtime consumers are inventoried and characterized.
- Do not add a new framework or dependency; use existing packages and the standard library.
- Keep the TUI monochrome engineering-console style: near-black surfaces, one restrained blue interaction accent, semantic amber/green/red, no card-heavy dashboard styling.
- Every refactor task must have focused tests before implementation and must leave the full observable behavior unchanged.

---

## Current Architecture and Data Flow

```text
python -m finai
  finai.__main__ -> finai.cli
    parse_arguments -> FinAIRepl -> AgentLoop -> RegistryToolRunner
    TTY -> FinAIApp -> typed ResearchEvent stream -> reducer/renderers
    one-shot -> plain/json renderer
    non-TTY -> legacy FinAIRepl.run/research compatibility loop

POST /api/chat
  app.routes.chat -> compatibility orchestrator adapter -> AgentLoop
  AgentLoop -> HiveService + registered tools -> providers / deterministic quant
  ResearchEvent -> SSE StreamEvent

Legacy graph path
  PipelineOrchestrator -> LangGraph graph -> agents/data/quant -> StreamEvent

Persistence
  FinAIRepl -> SessionStore -> transcript/checkpoint/pending/context/trace/run JSON
```

The main cognitive-load hotspots are `backend/finai/app.py` (TUI composition,
commands, event consumption, task lifecycle, and approval handling),
`backend/finai/session.py` (session state, persistence, two runtime adapters,
and a legacy console loop), `backend/app/core/agent_loop/runtime.py`
(model-stream parsing, tool-call policy, event orchestration, and limits),
`backend/app/core/tools/tool_system.py` (catalog, handlers, delegation, and
execution), and `backend/app/core/orchestrator.py` (graph execution, auditing,
stream translation, and safety handling).

## Ranked Complexity Report

### P0 — No confirmed correctness regression may be introduced

1. **Runtime duplication and unclear authority**
   - **Location:** `backend/finai/session.py`, `backend/app/routes/chat.py`, `backend/app/core/orchestrator.py`, `backend/app/core/agent_loop/runtime.py`
   - **Problem:** AgentLoop is the production CLI/HTTP runtime while the graph remains a compatibility runtime, but adapters and comments make ownership easy to misread.
   - **Why difficult:** A bug fix can be applied to the wrong execution path or change only one event contract.
   - **Principles:** explicit behavior, separation of concerns, dependency direction.
   - **Improvement:** document and test a runtime matrix; keep one adapter per boundary; remove only proven-dead paths later.
   - **Risk:** high if code is deleted; low if first limited to contracts and characterization tests.

2. **Hidden external-resource state**
   - **Location:** `backend/app/core/node_resources.py`, imports of `resources`, `backend/app/core/tools/tool_system.py`
   - **Problem:** singleton/lazy service access and registry globals hide dependencies and allow test/process state to leak.
   - **Why difficult:** Constructors and imports do not reveal which provider is used or when resources are created.
   - **Principles:** explicit dependencies, testability, low coupling.
   - **Improvement:** introduce an explicit `RuntimeResources` container at runtime boundaries while keeping a compatibility `resources` accessor during migration.
   - **Risk:** high because graph nodes and tests patch singleton internals.

### P1 — Major maintainability problems

3. **FinAIApp is a UI controller plus command service**
   - **Location:** `backend/finai/app.py`
   - **Problem:** composition, keyboard actions, slash-command dispatch, event reduction, widget mounting, approval UI, and task cancellation live in one class.
   - **Why difficult:** UI changes require understanding asynchronous execution and persistent state at the same time.
   - **Principles:** single responsibility, cohesion.
   - **Improvement:** extract pure command formatting, command action functions, and event-to-widget projection helpers; retain Textual lifecycle in `FinAIApp`.
   - **Risk:** medium/high; preserve focus, queued prompts, cancellation, and approval tests.

4. **FinAIRepl combines session storage, runtime orchestration, and two renderers**
   - **Location:** `backend/finai/session.py`
   - **Problem:** one class owns history mutation, checkpoints, trace/run persistence, AgentLoop execution, legacy graph execution, approval continuation, and plain console output.
   - **Why difficult:** persistence side effects are interleaved with event interpretation and user interaction.
   - **Principles:** single responsibility, pure side effects at boundaries.
   - **Improvement:** extract `SessionState`, `SessionPersistence`, and `ResearchRunner` collaborators with narrow protocols; keep `FinAIRepl` as a compatibility facade.
   - **Risk:** high; use characterization tests around exact JSON payloads and event ordering.

5. **AgentLoop runtime has mixed parsing, policy, and orchestration**
   - **Location:** `backend/app/core/agent_loop/runtime.py`
   - **Problem:** provider event decoding, streamed tool-call assembly, approval policy, round limits, tool execution, checkpoint writes, and terminal events are interleaved.
   - **Why difficult:** a parser change can accidentally change approval or retry behavior.
   - **Principles:** separation of concerns, testability.
   - **Improvement:** extract pure `model_events.py` parsing/assembly and a small `tool_policy.py`; leave `AgentLoop.run` as the readable orchestration loop.
   - **Risk:** high for ordering; pure parsing extraction is lower risk.

6. **Tool system is a catalog and execution engine in one 700-line module**
   - **Location:** `backend/app/core/tools/tool_system.py`
   - **Problem:** tool schemas, registry state, handler registration, specialist delegation, quant scanner handlers, and result normalization share one file.
   - **Why difficult:** adding or debugging a tool requires scanning unrelated definitions and execution code.
   - **Principles:** cohesion, open/closed, explicit registration.
   - **Improvement:** split static catalog definitions from handler registration and execution; keep `ToolRegistry`, `ToolExecutor`, and compatibility globals stable.
   - **Risk:** medium/high because prompts and tests depend on exact names.

### P2 — Moderate complexity

7. **PipelineOrchestrator mixes graph execution and audit serialization**
   - **Location:** `backend/app/core/orchestrator.py`
   - **Problem:** input validation, greeting handling, graph event multiplexing, audit-safe payload shaping, loop accounting, and SSE translation are coupled.
   - **Improvement:** extract pure audit helpers and an event multiplexer; do not change graph scheduling or node behavior.
   - **Risk:** medium.

8. **Theme/configuration ownership is split**
   - **Location:** `backend/finai/theme.py`, `backend/finai/render.py`, `backend/finai/styles/*.tcss`
   - **Problem:** semantic colors exist in Python and TCSS, while layout/state selectors are spread across files.
   - **Improvement:** document token ownership, keep one semantic palette, and organize TCSS by tokens/layout/components/states/responsive rules.
   - **Risk:** low/medium; visual regression testing is required.

9. **Configuration and public imports are implicit**
   - **Location:** `backend/app/config`, package `__init__.py` files, `.vscode/launch.json`, README commands.
   - **Problem:** a developer cannot always tell which module is public, which settings are required, or which PYTHONPATH is assumed.
   - **Improvement:** define supported entrypoints and package exports, add a configuration reference, and keep VS Code launch targets aligned.
   - **Risk:** low.

## Target Module Ownership

```text
backend/
├── finai/
│   ├── __main__.py             # package launcher only
│   ├── cli.py                  # argv, terminal capability, startup/cleanup
│   ├── session.py              # compatibility facade for session operations
│   ├── session_state.py        # typed mutable conversation/run state
│   ├── session_runtime.py      # ResearchRunner; AgentLoop event stream
│   ├── session_persistence.py  # transcript/checkpoint/trace/run side effects
│   ├── app.py                  # Textual lifecycle and composition only
│   ├── app_commands.py         # named slash-command operations
│   ├── app_events.py           # event-to-presentation projection helpers
│   ├── commands.py             # command vocabulary/parser/help
│   ├── render.py               # pure Rich renderables
│   ├── session_store.py        # existing JSON/artifact format boundary
│   └── styles/                 # tokens, layout, components, documentation
├── app/
│   ├── core/agent_loop/
│   │   ├── runtime.py          # high-level bounded loop
│   │   ├── model_events.py     # pure provider chunk/event parsing
│   │   └── tool_policy.py      # approval/limits policy
│   ├── core/tools/
│   │   ├── catalog.py          # tool definitions only
│   │   ├── handlers.py          # handler functions/delegation
│   │   └── tool_system.py      # registry/executor compatibility facade
│   ├── core/resources.py       # explicit RuntimeResources container
│   ├── core/orchestrator.py    # graph compatibility orchestration
│   └── routes/chat.py          # HTTP request/SSE adapter only
├── agents/                     # specialist research nodes
├── data/                       # providers, normalization, source pipeline
└── quant/                      # deterministic calculations and scanners
```

Do not create every file in this tree up front. Each file is introduced only
when a focused extraction has tests and reduces the parent module's cognitive
load.

## Implementation Tasks

### Task 1: Establish characterization coverage and runtime matrix

**Files:**
- Create: `backend/tests/unit/test_runtime_matrix.py`
- Create: `backend/tests/unit/test_session_persistence_contract.py`
- Modify: `backend/tests/unit/test_terminal_cli_structure.py`
- Modify: `docs/refactoring-plan.md`

**Interfaces:**
- Tests call `finai.cli.parse_arguments`, `finai.cli.run_one_shot`, `finai.session.FinAIRepl`, `app.routes.chat._to_sse_event`, and `SessionStore`.
- Produces executable behavior locks for later extraction; no production API changes.

- [ ] **Step 1: Add tests for CLI mode selection without providers.** Assert `parse_arguments(["--plain", "--mode", "review", "Analyze", "INFY"])` returns the existing values and does not create `.finai`.
- [ ] **Step 2: Add tests for event mapping.** Build representative `ResearchEvent` instances for response delta, tool started/completed/failed, approval requested, run failed/cancelled/completed and assert exact `StreamEvent.type` and key fields.
- [ ] **Step 3: Add persistence contract tests.** With `tmp_path`, append user/assistant messages, write a checkpoint, pending approval, context, and run; reload using `SessionStore` and assert schema keys and ordering.
- [ ] **Step 4: Run focused tests.** `PYTHONPATH=backend .venv/bin/pytest -q backend/tests/unit/test_runtime_matrix.py backend/tests/unit/test_session_persistence_contract.py backend/tests/unit/test_terminal_*.py`.
- [ ] **Step 5: Record runtime matrix.** Document CLI interactive, CLI one-shot, CLI non-TTY, HTTP, and graph compatibility consumers in `docs/refactoring-plan.md`.

### Task 2: Extract session persistence behind a narrow collaborator

**Files:**
- Create: `backend/finai/session_persistence.py`
- Modify: `backend/finai/session.py`
- Test: `backend/tests/unit/test_session_persistence_contract.py`

**Interfaces:**
- Add `SessionPersistence(store: SessionStore, root: Path, session_id: str)`.
- Methods: `load_history() -> list[Message]`, `append_message(message: Message) -> None`, `write_checkpoint(payload: dict[str, Any]) -> None`, `write_pending(payload: dict[str, Any]) -> None`, `clear_pending() -> None`, and `write_run(query: str, run_id: str, status: str, events: list[dict[str, Any]]) -> None`.
- `FinAIRepl` delegates side effects to this collaborator and remains import-compatible.

- [ ] **Step 1: Write delegation tests** that monkeypatch a fake persistence object and assert `FinAIRepl` calls it for message, checkpoint, pending, and run writes.
- [ ] **Step 2: Move only file-writing code** from `_write_session`, `_write_run`, and repeated message/pending calls; preserve temporary-file replacement and JSON shape.
- [ ] **Step 3: Keep `SessionStore` as the format owner**; do not duplicate path construction or schema logic in the new class.
- [ ] **Step 4: Run persistence, terminal session, and safety tests.** `PYTHONPATH=backend .venv/bin/pytest -q backend/tests/unit/test_terminal_session_store.py backend/tests/unit/test_terminal_safety.py backend/tests/unit/test_session_persistence_contract.py`.

### Task 3: Extract the AgentLoop session runner

**Files:**
- Create: `backend/finai/session_runtime.py`
- Modify: `backend/finai/session.py`
- Test: `backend/tests/unit/test_terminal_session_runtime.py`

**Interfaces:**
- Add `ResearchRunner(hive_service: HiveService, mode: str, tool_registry: ToolRegistry, tool_executor: ToolExecutor)`.
- Method: `stream(history: list[Message], query: str, conversation_id: UUID, pending: dict[str, Any] | None, on_message: Callable[[Message], None], on_checkpoint: Callable[[dict[str, Any]], None]) -> AsyncIterator[ResearchEvent]`.
- `FinAIRepl._agent_loop_stream` becomes a compatibility adapter that prepares history and delegates execution/persistence decisions.

- [ ] **Step 1: Add fake model/tool tests** for normal completion, approval request, rejection, cancellation, and failed run; assert event ordering and status values.
- [ ] **Step 2: Move only AgentLoop construction and event iteration** into `ResearchRunner`; do not move `SessionStore` calls yet.
- [ ] **Step 3: Keep pending approval semantics**: approval IDs come from the checkpoint and rejection yields `RunCancelled(reason="request rejected by user")`.
- [ ] **Step 4: Run `backend/tests/unit/test_agent_loop.py`, terminal stream/supervisor tests, and the new runtime tests.**

### Task 4: Separate legacy graph compatibility from the production session path

**Files:**
- Create: `backend/finai/legacy_runtime.py`
- Modify: `backend/finai/session.py`
- Test: `backend/tests/unit/test_terminal_legacy_runtime.py`

**Interfaces:**
- Add `LegacyResearchRunner(orchestrator: PipelineOrchestrator)`.
- Method: `stream(query: str, history: list[Message], mode: str, conversation_id: UUID) -> AsyncIterator[ResearchEvent]`.
- `FinAIRepl` calls this runner only when `self.orchestrator` is an injected non-default compatibility implementation.

- [ ] **Step 1: Characterize the injected-orchestrator branch** with a fake async stream and assert history append, approval continuation, and trace persistence.
- [ ] **Step 2: Move `adapt_legacy_stream` invocation and legacy approval query selection** into `LegacyResearchRunner`.
- [ ] **Step 3: Leave the `PipelineOrchestrator` class and HTTP adapter untouched** except for type imports until runtime consumers are measured.
- [ ] **Step 4: Run legacy terminal tests plus orchestrator streaming-safety tests.**

### Task 5: Modularize the Textual controller without adding a framework

**Files:**
- Create: `backend/finai/app_commands.py`
- Create: `backend/finai/app_events.py`
- Modify: `backend/finai/app.py`
- Test: `backend/tests/unit/test_terminal_app_commands.py`

**Interfaces:**
- `app_commands.py`: pure helpers `format_status(state: PresentationState) -> str`, `format_history(history: Sequence[Message]) -> str`, and `format_trace(records: Sequence[dict[str, Any]], path: Path) -> str`.
- `app_events.py`: `event_to_state(state: PresentationState, event: ResearchEvent) -> PresentationState` and `activity_text(state: PresentationState) -> Text` for projection-only behavior.
- `FinAIApp` retains Textual callbacks, widget lookup, task ownership, and screen navigation.

- [ ] **Step 1: Add pure tests** for debug/status/history/trace formatting and event projection across completed, failed, cancelled, and approval states.
- [ ] **Step 2: Move formatting branches** from `_command` and `_consume` into helpers; preserve visible strings and CSS classes.
- [ ] **Step 3: Replace the long `_command` chain** with named private methods (`_command_help`, `_command_trace`, `_command_sessions`, `_command_resume`, `_command_context`) that call the helpers; do not create a generic command framework.
- [ ] **Step 4: Keep composer behavior stable** while applying the prior UI requirement: Enter submits, Shift+Enter inserts a newline, and the composer is the primary bottom control; the send button is removed only after an interaction test confirms Enter submission.
- [ ] **Step 5: Run all terminal app/rendering/state tests and a Textual smoke test at 80, 120, 160, and 200 columns.**

### Task 6: Split AgentLoop parsing from orchestration

**Files:**
- Create: `backend/app/core/agent_loop/model_events.py`
- Create: `backend/app/core/agent_loop/tool_policy.py`
- Modify: `backend/app/core/agent_loop/runtime.py`
- Test: `backend/tests/unit/test_agent_loop_model_events.py`
- Test: `backend/tests/unit/test_agent_loop_policy.py`

**Interfaces:**
- `model_events.py`: `merge_chunk_tool_calls(calls: dict[int, dict[str, Any]], chunk: Any) -> None`, `sanitize_tool_calls(calls: Sequence[dict[str, Any]]) -> list[dict[str, Any]]`, `parse_tool_call(call: Mapping[str, Any]) -> tuple[str, str, dict[str, Any]]`, and `tool_call_identity(call: Mapping[str, Any]) -> tuple[str, str]`.
- `tool_policy.py`: `requires_approval(tool_name: str, call_id: str, approved: set[str], mode: str) -> bool`.
- `runtime.py` imports these pure functions and keeps `AgentLoop.run`/`_stream_model` orchestration.

- [ ] **Step 1: Move existing parser tests or add fixtures** for malformed JSON, fragmented tool calls, missing IDs, and non-dict arguments.
- [ ] **Step 2: Extract functions without changing exception types or messages.**
- [ ] **Step 3: Replace inline approval logic with `requires_approval` and assert data/news/research/market policy remains unchanged.**
- [ ] **Step 4: Run AgentLoop, model-stream, safety, and terminal stream tests.**

### Task 7: Split tool catalog and handlers while preserving the compatibility facade

**Files:**
- Create: `backend/app/core/tools/catalog.py`
- Create: `backend/app/core/tools/handlers.py`
- Modify: `backend/app/core/tools/tool_system.py`
- Modify: `backend/app/core/agent_loop/runtime.py`
- Test: `backend/tests/unit/test_tool_catalog.py`
- Test: `backend/tests/unit/test_tool_system.py`

**Interfaces:**
- `catalog.py`: `predefined_tool_definitions() -> tuple[ToolDefinition, ...]`.
- `handlers.py`: `register_predefined_handlers(executor: ToolExecutor, resources: NodeResources) -> None`.
- `tool_system.py` continues exporting `ToolNamespace`, `ToolDefinition`, `ToolResult`, `ToolRegistry`, `ToolExecutor`, `tool_registry`, `tool_executor`, and `initialize_tool_system`.

- [ ] **Step 1: Add catalog tests** asserting unique full names, prompt-referenced names, and stable definition ordering.
- [ ] **Step 2: Move static definitions** into `catalog.py`; keep registry behavior, `clear()`, and `is_initialized` unchanged.
- [ ] **Step 3: Move handler registration and quant scanner handlers** into `handlers.py`; preserve `ToolResult` normalization and delegation names.
- [ ] **Step 4: Keep initialization explicit** at CLI/HTTP/runtime startup and verify importing `tool_system` does not initialize the catalog.
- [ ] **Step 5: Run tool registry/system, AgentLoop, graph contract, and prompt validation tests.**

### Task 8: Replace the implicit resource singleton through an explicit migration boundary

**Files:**
- Create: `backend/app/core/resources.py`
- Modify: `backend/app/core/node_resources.py`
- Modify: `backend/app/core/agent_loop/runtime.py`
- Modify: `backend/app/routes/chat.py`
- Modify: `backend/finai/cli.py`
- Test: `backend/tests/unit/test_runtime_resources.py`

**Interfaces:**
- Add `RuntimeResources(llm_service: HiveService, yf_fetcher: YFinanceFetcher)` as a typed dataclass.
- Add `build_runtime_resources() -> RuntimeResources` for application startup.
- Keep `node_resources.resources` as a deprecated compatibility adapter until all graph consumers accept an injected `RuntimeResources`.

- [ ] **Step 1: Add tests** proving resource construction is explicit and fake resources can be injected into AgentLoop/tool handlers.
- [ ] **Step 2: Pass `RuntimeResources` into the production `RegistryToolRunner`** instead of importing the singleton inside `execute`.
- [ ] **Step 3: Pass the same container from CLI and HTTP startup** so one run has one provider/fetcher ownership boundary.
- [ ] **Step 4: Update graph nodes incrementally** to accept the injected container while preserving the compatibility global for un-migrated callers.
- [ ] **Step 5: Run resource-patching tests, HTTP route tests, AgentLoop tests, and graph tests.**

### Task 9: Isolate pure graph audit/event helpers

**Files:**
- Create: `backend/app/core/graph_audit.py`
- Create: `backend/app/core/graph_events.py`
- Modify: `backend/app/core/orchestrator.py`
- Test: `backend/tests/unit/test_graph_audit.py`
- Test: `backend/tests/unit/test_graph_event_bridge.py`

**Interfaces:**
- `graph_audit.py`: move `_audit_safe_payload`, `_audit_safe_value`, `_build_audit_context`, `_is_missing_audit_context_value`, `_audit_log_data`, and `_loop_snapshot` as module-level pure functions.
- `graph_events.py`: `event_metadata(event: Mapping[str, Any]) -> dict[str, Any]` and graph/token queue multiplexing helpers with no audit side effects.
- `PipelineOrchestrator` remains the public class and delegates to these helpers.

- [ ] **Step 1: Add exact input/output tests** for nested payload truncation, missing audit values, loop snapshots, and event metadata limits.
- [ ] **Step 2: Move pure functions mechanically** and preserve keys, truncation limits, and ordering.
- [ ] **Step 3: Extract only queue multiplexing** from `execute_query`; leave graph scheduling, node configuration, and safety handling in place.
- [ ] **Step 4: Run all orchestrator trace/streaming/query-scope tests.**

### Task 10: Make the TUI theme and layout discoverable

**Files:**
- Modify: `backend/finai/theme.py`
- Modify: `backend/finai/render.py`
- Modify: `backend/finai/styles/tokens.tcss`
- Modify: `backend/finai/styles/layout.tcss`
- Modify: `backend/finai/styles/components.tcss`
- Modify: `backend/finai/styles/README.md`
- Test: `backend/tests/unit/test_terminal_theme.py`

**Interfaces:**
- Keep `CSS_VARIABLES`, `COLORS`, and `FINAI_RICH_THEME` import-compatible.
- Define semantic tokens for background, surfaces, text, accent, process, success, warning, and error; derive Rich aliases from the same Python palette.

- [ ] **Step 1: Add token tests** for required names and monochrome palette constraints.
- [ ] **Step 2: Document selector ownership**: tokens only define variables, layout only defines geometry/breakpoints, components only define widget surfaces/states.
- [ ] **Step 3: Keep the right context rail at approximately 17% width** and remove the standalone send button only if Task 5 interaction tests pass.
- [ ] **Step 4: Add visual smoke notes** for 80/120/160/200-column resize, hidden context, collapsed navigation, focus rail, and running/completed/failed states.

### Task 11: Define public entrypoints, configuration, and developer navigation

**Files:**
- Create: `docs/architecture/finai-runtime.md`
- Create: `docs/architecture/module-map.md`
- Modify: `README.md`
- Modify: `.vscode/launch.json`
- Modify: `backend/finai/__init__.py`
- Test: `backend/tests/unit/test_entrypoints.py`

**Interfaces:**
- Supported CLI entrypoint remains `python -m finai`.
- Documented HTTP entrypoint remains `app.main:app`.
- Public compatibility import `from finai.__main__ import FinAIRepl` remains supported until a deprecation decision is recorded.

- [ ] **Step 1: Add import/launch tests** for `python -m finai --help`, `finai.cli.main`, `app.main:app`, and the compatibility `FinAIRepl` import.
- [ ] **Step 2: Write the module map** with one paragraph per module: responsibility, inputs, outputs, dependencies, and safe change locations.
- [ ] **Step 3: Update README commands** to use the repository `.venv` and `PYTHONPATH=backend` conventions; explain AgentLoop versus graph compatibility.
- [ ] **Step 4: Keep VS Code launch configurations aligned** with the module entrypoint and `.env` behavior.

### Task 12: Full verification and removal review

**Files:**
- Modify: `docs/refactoring-plan.md`
- Modify: `docs/architecture/finai-runtime.md`

- [ ] **Step 1: Run focused suites after each task.**
- [ ] **Step 2: Run `PYTHONPATH=backend .venv/bin/python -m finai --help`.
- [ ] **Step 3: Run `.venv/bin/pytest -q backend/tests` once with a visible timeout and record the exact result; do not run duplicate suites.
- [ ] **Step 4: Run `.venv/bin/ruff check backend evals` and `.venv/bin/python -m compileall -q backend evals`.
- [ ] **Step 5: Run mypy with the repository’s configured import path and record pre-existing missing-stub/import failures separately from refactor failures.
- [ ] **Step 6: Review imports and delete only adapters proven unused by tests and runtime inventory.
- [ ] **Step 7: Update the remaining technical-debt section with any unresolved singleton, graph, UI, or type-checking work.

## Definition of Done

- A new engineer can identify the CLI, HTTP, production runtime, compatibility runtime, session persistence, TUI, provider, and quant modules from the documented module map.
- `FinAIApp` is responsible for Textual lifecycle and widget mutation, not formatting algorithms or persistence.
- `FinAIRepl` remains a small compatibility facade over session persistence and a selected runner.
- AgentLoop parsing/policy helpers are pure and independently tested.
- Tool catalog and tool handlers are separate while existing exports remain stable.
- Resource construction is explicit at production startup; the compatibility singleton is isolated and documented.
- Existing CLI, HTTP SSE, approval, cancellation, persistence, trace, and deterministic quant tests pass.
- The previous monochrome TUI remains intact: restrained accent, clear message/event surfaces, right rail near 17%, bottom composer behavior, and responsive breakpoints.
- No unsupported “full suite passed” claim is made when integration tests time out or environment/import issues remain.

## Deliberate Non-Goals

- Do not rewrite all agents into generic domain/application/infrastructure folders.
- Do not remove LangGraph or `PipelineOrchestrator` before a consumer table proves safe deletion.
- Do not create a command-dispatch framework, dependency-injection container, repository interface hierarchy, or plugin system.
- Do not change financial formulas, provider selection, model prompts, retry limits, approval vocabulary, or event schema as part of modularization.
