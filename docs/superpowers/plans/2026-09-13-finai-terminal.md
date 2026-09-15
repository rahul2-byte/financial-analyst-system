# FIN-AI Terminal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an event-driven interactive FIN-AI terminal with typed events, deterministic presentation state, safe rendering, cancellation, approvals, sessions, and non-interactive fallback.

**Architecture:** `PipelineOrchestrator` produces typed application events. A run controller sequences and persists them. Textual and plain renderers consume the same events, while the existing FastAPI route receives a compatibility stream adapter.

**Tech Stack:** Python 3.12, Pydantic v2, asyncio, LangGraph, Textual, Rich, pytest, uv

**Spec:** `docs/superpowers/specs/2026-09-13-finai-terminal-design.md`

## Global Constraints

- Financial and provider modules must not import terminal libraries.
- Only public final-answer text may be streamed to the user.
- No fabricated timing, source, token, progress, or cost values.
- Preserve `NO_COLOR` and non-TTY behavior.
- Sanitize untrusted terminal text and URLs.
- Preserve current FastAPI frontend compatibility.
- Do not alter deterministic quant calculations.

---

### Task 1: Typed events and presentation reducer

**Files:**
- Create: `backend/app/events/models.py`
- Create: `backend/app/events/sequencing.py`
- Create: `backend/app/events/__init__.py`
- Create: `backend/finai/state.py`
- Test: `backend/tests/unit/test_research_events.py`
- Test: `backend/tests/unit/test_terminal_state.py`

**Interfaces:**
- Produces: `ResearchEvent`, `EventFactory.next(...)`, `PresentationState`, `reduce_event(state, event)`.
- Consumes: Pydantic v2 and Python standard-library UUID/date types.

- [x] Write tests proving required metadata, monotonic sequencing, valid terminal transitions, duplicate suppression, and invalid sequence handling.
- [x] Run the focused event/reducer tests and confirm the initial failures were missing modules.
- [x] Implement the discriminated event union, event factory, run phases, activity/source records, and pure reducer.
- [x] Run the focused tests and confirm they pass.

### Task 2: Safe semantic event stream

**Files:**
- Create: `backend/app/events/mapping.py`
- Modify: `backend/app/core/orchestrator.py`
- Modify: `backend/app/services/hive_service.py`
- Modify: `backend/app/models/response_models.py`
- Modify: `backend/app/routes/chat.py`
- Test: `backend/tests/unit/test_orchestrator_research_events.py`
- Test: `backend/tests/unit/test_sse_event_adapter.py`

**Interfaces:**
- Consumes: `EventFactory`, LangGraph lifecycle callbacks, existing final output and provider telemetry.
- Produces: `PipelineOrchestrator.stream_research(...) -> AsyncIterator[ResearchEvent]` and `to_legacy_stream_event(event)`.

- [x] Write focused tests for final-only text streaming, approval state, and legacy event mapping.
- [x] Run the focused adapter tests and confirm the initial contract failure.
- [x] Add semantic mapping while retaining `execute_query()` as the compatibility adapter.
- [x] Ensure terminal clients ignore intermediate LLM tokens and receive only report text.
- [x] Run focused orchestrator and terminal streaming tests.

### Task 3: Session controller, commands, and plain mode

**Files:**
- Create: `backend/finai/controller.py`
- Create: `backend/finai/sessions.py`
- Create: `backend/finai/commands.py`
- Create: `backend/finai/safety.py`
- Create: `backend/finai/plain.py`
- Modify: `backend/finai/__main__.py`
- Modify: `pyproject.toml`
- Test: `backend/tests/unit/test_terminal_controller.py`
- Test: `backend/tests/unit/test_terminal_commands.py`
- Test: `backend/tests/unit/test_terminal_safety.py`

**Interfaces:**
- Consumes: `AsyncIterator[ResearchEvent]`.
- Produces: `RunController.run(query)`, `RunController.cancel()`, `CommandRegistry`, `sanitize_terminal_text()`, and deterministic plain/JSON renderers.

- [ ] Write tests for history persistence, approval continuation under one run ID, command parsing, non-TTY output, `NO_COLOR`, sanitization, and cancellation.
- [ ] Run focused tests and confirm missing behavior fails.
- [ ] Implement controller and local artifact repository without recursive research calls.
- [x] Add one-shot positional query output with `--plain`/`--json` flags.
- [x] Run focused tests and CLI help/headless smoke checks.

### Task 4: Textual interactive terminal

**Files:**
- Create: `backend/finai/app.py`
- Create: `backend/finai/render.py`
- Create: `backend/finai/theme.py`
- Modify: `backend/finai/__main__.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Test: `backend/tests/unit/test_terminal_app.py`
- Test: `backend/tests/unit/test_terminal_rendering.py`

**Interfaces:**
- Consumes: `RunController`, `PresentationState`, `ResearchEvent`, and `CommandRegistry`.
- Produces: `FinAIApp`, responsive renderables, composer, activity view, source view, approval/clarification screens, and status line.

- [x] Write Textual headless tests for submit, streamed output, and Ctrl+C.
- [ ] Run focused tests and confirm missing UI failures.
- [x] Add Textual and Rich through uv, then implement the minimal component tree and event-driven shell.
- [x] Restore terminal state through Textual cancellation and terminal outcome handling.
- [x] Run focused headless Textual tests.

### Task 5: Verification, documentation, and compatibility

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/failure-taxonomy.md`
- Modify: affected existing stream tests

**Interfaces:**
- Consumes: completed interactive, plain, JSON, and SSE adapters.
- Produces: documented commands, keyboard behavior, event architecture, and verified acceptance record.

- [ ] Run all new terminal and event tests.
- [ ] Run existing orchestrator, Hive, route, graph, and session-adjacent tests.
- [ ] Run Ruff, formatting check, mypy on new modules, compileall, and CLI smoke checks.
- [ ] Document interactive, plain, JSON, cancellation, approval, debugging, and known limitations.
- [ ] Compare observed behavior against every acceptance criterion and report any unverified live-provider behavior honestly.
