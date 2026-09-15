# FIN-AI simplification plan

Status: implementation in progress. AgentLoop is now the production runtime;
the former LangGraph/PipelineOrchestrator path and graph-specific tests have
been removed. Remaining work is limited to compatibility cleanup and typing.

## Objective and scope

Make execution and ownership easier to follow while preserving CLI commands,
HTTP streaming, session artifacts, approval behavior, cancellation, and quant
outputs. Use incremental changes; do not migrate frameworks or reorganize the
entire backend into generic domain/application/infrastructure directories.

This plan is based on inspection of the entrypoints, terminal modules, HTTP
adapter, session store, runtime and tool-system declarations, existing tests,
and repository guidance. It is not a completed line-by-line audit of every
financial agent. Deeper runtime changes require the inspection gates below.

## Current execution and data flow

```text
python -m finai
  finai/__main__.py: arguments, logging, FinAIRepl construction
    interactive TTY -> FinAIApp -> typed_stream
    positional query -> typed_stream -> plain/JSON output
    non-TTY input -> legacy console loop -> research

POST /api/chat
  app/routes/chat.py -> compatibility adapter -> AgentLoop

Production typed_stream -> AgentLoop
  model stream + skill selection + registered tools
  tools -> providers / financial agents / deterministic quant
  typed ResearchEvent -> TUI reducer/renderers or HTTP SSE adapter
  CLI additionally persists transcript, checkpoints, trace, run artifacts

AgentLoop
  model stream + skill selection + registered tools
  shared agent contracts -> providers / deterministic quant
```

The CLI owns local conversation persistence. The TUI owns presentation and
interaction. AgentLoop owns model/tool iteration. SessionStore owns filesystem
formats. Quant modules own calculations. The older graph is not the default
production CLI execution path; documentation currently obscures this distinction.

## Ranked complexity report

### P1: overloaded CLI entrypoint

- Location: `backend/finai/__main__.py` (510 lines at inspection).
- Problem: CLI parsing, resource setup/cleanup, session state, persistence,
  production streaming, and legacy console behavior share one module.
- Understanding cost: following startup requires reading two execution models
  and several storage formats; constructors also perform filesystem work.
- Principles: single responsibility, explicit side effects, cohesion.
- Improvement: thin launcher, cohesive startup module, session controller;
  preserve legacy behavior until its callers and contracts are characterized.
- Risk: medium; tests import FinAIRepl directly from __main__.

### P1: runtime story and compatibility paths are unclear

- Location: README, `app/routes/chat.py`, `finai/__main__.py`,
  `app/core/orchestrator.py`, `app/core/agent_loop/runtime.py`.
- Problem: documentation describes the graph as the shared main path, while
  production CLI and HTTP use AgentLoop through different adapters.
- Understanding cost: developers can change the wrong runtime while debugging.
- Principles: explicit behavior, discoverability, separation of concerns.
- Improvement: document actual paths and inventory compatibility consumers
  before considering deletion or consolidation.
- Risk: low for documentation, high for removing graph/compatibility code.

### P1: presentation controller has several independent responsibilities

- Location: `backend/finai/app.py` (623 lines at inspection).
- Problem: composition, command dispatch, event consumption, task lifecycle,
  session switching, and diagnostic formatting are interleaved.
- Understanding cost: a command or cancellation change requires following
  mutable UI state and runtime task references across a large class.
- Principles: cohesion, explicit state transitions, separation of concerns.
- Improvement: first extract pure diagnostic formatting and named command
  methods; introduce a separate module only for a cohesive group of operations.
  Retain Textual lifecycle and widget mutation in FinAIApp.
- Risk: medium/high; focus, queued input, approval, and cancellation interact.

### P1: implicit tool/resource initialization

- Location: `app/core/tools/tool_system.py`, `app/core/node_resources.py`.
- Problem: module-level tool initialization and singleton resources hide
  dependency creation and shared mutation behind imports.
- Understanding cost: imports can initialize registrations; tests can depend
  on process-wide state and initialization order.
- Principles: explicit dependencies, minimal mutable global state.
- Improvement: characterize initialization first, then expose one explicit
  startup operation using the existing registry/executor objects.
- Risk: high; framework imports and dynamically registered handlers matter.

### P2: large runtime and tool modules

- Location: `agent_loop/runtime.py` (647 lines), `tool_system.py`,
  `orchestrator.py` (821 lines).
- Problem: stream parsing, tool definitions, execution policy, and iteration
  are expensive to inspect together.
- Principles: cohesion and readable control flow.
- Improvement: trace complete call paths before extraction; isolate pure
  model-chunk/tool-call parsing and cohesive tool catalog definitions only if
  this makes the main workflow shorter and clearer.
- Risk: high for execution ordering; lower for pure parsing with fixtures.

### P2: duplicated presentation configuration

- Location: `finai/theme.py`, `render.py`, `styles/*.tcss`.
- Problem: CSS_VARIABLES and COLORS duplicate semantic colors, and some
  literal colors remain outside the token layer. Layout also contains styling.
- Principles: DRY, predictable ownership.
- Improvement: one palette with derived Rich aliases; format TCSS with one
  declaration per line and group shell, component, state, responsive rules.
- Risk: low/medium; colors, specificity, and terminal geometry need visual checks.

### Correctness concerns to investigate separately

Do not quietly change these during structural refactoring:

- HTTP adapter reconstructs ChatRequest from messages; verify whether model
  and max_tokens overrides are lost before treating this as a confirmed bug.
- Non-TTY fallback calls research through an orchestrator initialized as None;
  characterize the supported fallback and its current failure output.
- TUI terminal-event handling hides the activity panel; verify failure details
  remain discoverable, particularly when no assistant response was produced.
- Tool/result CSS classes may accumulate across events; test consecutive state
  transitions before changing their behavior.

## Proposed module ownership

```text
backend/
  finai/
    __main__.py       package launcher; compatible public imports
    cli.py            argument parsing, output-mode selection, resource cleanup
    session.py        conversation state, checkpoints, runtime event persistence
    app.py            Textual lifecycle, widgets, commands, event presentation
    session_store.py  existing filesystem formats
    state.py          existing event-to-presentation reducer
    render.py         existing Rich output and pure diagnostic formatting
    commands.py       existing command vocabulary and parsing
    screens.py        existing modal interaction
    theme.py          shared palette
    styles/           documented layout and component rules
  app/
    routes/           HTTP input and SSE translation
    core/agent_loop/  shared production model/tool workflow
    core/tools/       tool definitions and execution
    events/           typed execution events and trace ledger
  agents/             financial/research operations
  data/               external providers and normalization
  quant/              deterministic financial calculations
```

Proposed module contracts:

| Module | Inputs | Outputs | Dependencies and reason |
|---|---|---|---|
| __main__ | module execution | exit status | cli; predictable package entrypoint |
| cli | argv, terminal capabilities | selected execution mode | session, TUI, plain renderers; owns startup and cleanup |
| session | query, session ID, mode | ResearchEvent stream, artifacts | existing runtime and SessionStore; owns conversation lifecycle |
| app | typed events, user actions | terminal display, callback requests | Textual, state/render; owns interaction |
| session_store | typed messages, artifact payloads | persisted/read records | filesystem, ledger; preserves storage contract |
| theme | fixed palette definitions | CSS/Rich styles | no runtime services; one source for visual values |

Do not add an interface/factory hierarchy. Preserve useful existing protocols
where tests substitute model streams or tool execution.

## Incremental implementation sequence

### 1. Baseline and deeper inspection

Record the dirty worktree without committing unrelated work. Inventory imports,
CLI flags, public re-exports, dynamic registration, scripts, and API consumers.
Read each proposed change boundary completely. Run the existing backend suite,
lint, format check, and mypy; record pre-existing failures and hanging tests.
Do not run duplicate full-suite processes. Observe completion through session IDs.

### 2. Protect observable behavior

Add characterization coverage for TTY/non-TTY/one-shot dispatch, help parsing,
provider cleanup on success/error/cancellation, pending approval continuation,
session switching, trace ordering, and transcript persistence where absent.
Use fake model/tool streams; do not require live APIs. Compare stored payloads
with existing schema while normalizing timestamps and random IDs.

### 3. Clarify startup and session ownership

Move startup to cli.py and conversation lifecycle to session.py. Keep FinAIRepl
as its existing class name initially and re-export it from __main__ to preserve
imports. Name startup operations by purpose: parse_arguments, run_one_shot,
run_interactive. Keep one clear provider cleanup boundary. Verify mode dispatch
and artifact behavior before changing internal duplication.

Trade-off: two cohesive files are added; startup becomes readable independently
of conversation persistence. A move alone does not solve session complexity.

### 4. Simplify session and TUI operations locally

Extract only shared conversation concepts with identical semantics, such as
append-to-history-and-transcript. Do not merge production and legacy handling
where statuses, approval semantics, or artifact payloads differ. Turn long
command branches into named operations without introducing a command framework.
Keep error-policy fixes separate from mechanical refactors.

### 5. Address deeper boundaries after characterization

Inventory all registry initialization consumers before moving initialization
to startup. Extract pure stream parsing if it reduces runtime reading cost.
Retain graph execution until a consumer/migration table proves removal safe.
Leave quant algorithms and financial thresholds unchanged.

### 6. Consolidate presentation configuration and documentation

Derive Rich color aliases from existing tokens without changing palette values.
Keep TCSS files readable and document selector specificity, units, responsive
classes, and common edits. Correct README commands to include backend PYTHONPATH.
Document CLI versus API flow, breakpoint locations, artifact ownership, settings,
and where new financial logic belongs. Update VS Code configuration only if the
module entrypoint contract changes; it should continue launching module finai.

### 7. Verify and review

Run focused tests after each logical change, then the full suite once. Compare
CLI help, import compatibility, SSE event schema, persisted artifacts, and
deterministic quant outputs. Exercise Textual at 80, 120, 160, and 200 columns,
including long content, focus, resize, running/completed/failed/cancelled states.
Capture and inspect representative frames; passing widget-existence tests is
not evidence of visual quality.

Use these checks from the repository root with its installed environment:

```sh
PYTHONPATH=backend .venv/bin/python -m finai --help
.venv/bin/pytest backend/tests
.venv/bin/ruff check backend evals
.venv/bin/ruff format --check backend evals
.venv/bin/mypy backend
.venv/bin/python -m compileall -q backend evals
```

Report full-tree pre-existing failures separately from changed-file regressions.
Live provider behavior and VS Code F5 execution require separate verification;
do not infer them from local test results.

## Review boundaries and acceptance criteria

Each phase should produce a small reviewable diff with its own evidence. No bulk
rename campaign, no new dependencies, and no formatting unrelated files. Do not
create modules solely to reach a line-count target.

Success means a developer can identify startup, runtime, persistence, UI, and
quant ownership from README and the main execution path. Existing commands,
approval/cancellation behavior, response/event schemas, and artifact formats
must remain compatible. Reconsider any new helper that only adds indirection.

The final implementation report must list actual changes, renamed public
symbols, retained compatibility, removed duplication, exact checks and outcomes,
and remaining debt. The inspection above does not establish that legacy code is
dead, that all error behavior is correct, or that the whole backend is type-clean.
