# FIN-AI Conversational Finance Agent — Implementation Plan

> For agentic workers: implement in dependency order using executing-plans or subagent-driven-development with review between milestones. Checkboxes describe deliverables, not claims of completed work.

**Goal:** Build a persistent conversational finance assistant that answers, researches, calculates, asks questions, and revises investigations through tools and optional specialists.

**Architecture:** One application-owned conversational agent loop proposes typed actions; a Python harness validates and executes them. Durable session state owns conversation, pending interactions, tasks, and evidence. Textual and plain output consume the same typed events.

**Tech stack:** Existing Python, Pydantic v2, asyncio, Textual, Rich, httpx, NumPy/Pandas, pytest. Use stdlib SQLite for transactional session state; retain project-local artifact files. No new agent framework is required.

**Spec:** The product specification and interfaces are embedded below. This plan supersedes the mandatory top-level graph workflow in earlier terminal plans. It does not authorize immediate deletion of working financial code.

## 1. Product contract

FIN-AI is a personal finance research assistant with a continuous conversation. A greeting requires no research; a definition may need no tools; a current market question requires fresh evidence; an investigation may require multiple tools and specialists. Follow-up questions can revise scope, challenge a conclusion, compare another company, or inspect a calculation.

The agent decides which capability to use from context. It does not send every financial question through five analysis agents. It can acknowledge useful actions concisely, but execution starts only when the harness accepts an action. A promise in assistant prose never marks work started or completed.

Initial supported scope: company and equity research, filings, news, financial concepts, market context, comparisons, user-supplied portfolio analysis, and reproducible calculations. Portfolio analysis requires supplied holdings and relevant assumptions. Brokerage execution remains outside this release, consistent with PROJECT_CONSTITUTION.md.

Global constraints:

- Python 3.11+; Pydantic v2 contracts; no terminal libraries imported by financial services.
- Financial calculations and indicators execute in Python. Source numbers must retain units, currency, dates, and provenance.
- Sessions, artifacts, configuration, and logs reside in the local project's `.finai/`.
- Default requested context budget: 250,000 tokens. Automatic compaction at approximately 90% of usable input capacity; manual `/compact` is independent of the threshold.
- No cost display or cost accounting subsystem. Context, output, action, time, and concurrency limits remain operational controls.
- Genuine public response streaming; no hidden reasoning display and no simulated token pacing.
- Cancel safely and preserve the session. Resume after app closure.
- User can ask clarification questions and revise scope naturally. Routine authorized retrieval does not need repeated permission prompts.
- Textual interactive mode and incremental plain/JSON output coexist.

## 2. Evidence from current repository

Inspected 2026-09-13. These are source findings, not a full runtime certification.

| Location | Finding | Consequence |
|---|---|---|
| `backend/app/core/graph/runtime/graph_builder.py` | Router-driven graph includes cycles | Calling it a DAG does not explain the defects; replace top-level policy for conversational flexibility |
| `backend/agents/orchestration/goal_node.py` | Waiting status is top-level; final_output can be a string | Orchestrator's dictionary-only waiting check misses genuine pauses |
| `backend/app/core/orchestrator.py` | Dictionary-only approval detection; final fallback split into 160-character pieces | Waiting can become completion; chunk count is not proof of live streaming |
| `backend/finai/stream_adapter.py` | Stage labels synthesize tool activity; text split again | UI activity can lack actual execution identity |
| `backend/app/services/hive_service.py` | Tool-call fragments extended into a list; usage returned before choices; finish reason not used for outcome | Tool arguments need assembly; mixed frames and truncation need proper handling |
| `backend/app/services/hive_service.py` | Transport retry can restart after emitted content | Duplicate response or action risk |
| `backend/finai/__main__.py` | One-shot collects every event before writing; pending approval uses a short phrase whitelist | Plain output buffers; conversation text is being used as a control protocol |
| `backend/finai/session_store.py` | Events persisted in write_run at end; resume may construct arbitrary paths; sorting uses IDs | Crash recovery, session selection, and path validation need hardening |
| `backend/finai/context_budget.py` | Character estimate; first 500 characters per dropped message become system text | No semantic summary guarantee, tool-pair integrity, or verified post-compaction bound |
| `backend/app/core/tools/tool_system.py` | Explicitly legacy; some handlers only delegate | Do not revive it unchanged as the agent execution engine |
| `backend/finai/supervisor.py` | Stream termination guard | This is not yet a conversational supervisor |

Earlier live probes established that Hive can deliver public content in separate SSE frames. They did not establish tool-calling compatibility, end-to-end research correctness, or reliable completion. These remain explicit release gates.

## 3. Target ownership and boundaries

```text
Textual composer / plain CLI / existing API
                  |
             SessionController
                  |
       conversational AgentRuntime
          |        |          |
      provider   tool runner  interaction policy
                   |
       data adapters / Python / specialists
                   |
        evidence + calculation artifacts
                   |
       durable records -> typed events -> clients
```

`SessionController` owns one active conversational turn per session, accepted user input, cancellation, and resume. `AgentRuntime` owns the model/action loop. `ToolRunner` owns actual invocation and operation lifecycle. `SessionStore` owns durable records. Presentation state is a projection, never the authority for approvals or task completion.

Use asyncio tasks and a bounded local event queue. No HTTP/SSE between local application components. Existing FastAPI can serialize the events for remote clients later through its current route. Do not make the web route a prerequisite for the terminal.

The conversation loop permits tool use, direct answers, and questions at any point. Small deterministic dependencies stay in ordinary Python functions or task prerequisites. Retain LangGraph only during migration; remove the dependency after its final production consumer has moved.

## 4. State and event contracts

Use independent state owners:

| Owner | States |
|---|---|
| Turn | active, waiting_for_input, waiting_for_approval, cancelling, completed, failed, cancelled, interrupted |
| Task | queued, running, blocked, succeeded, failed, cancelled, interrupted |
| Operation | queued, running, retrying, succeeded, failed, cancelled, interrupted |
| Message | streaming, complete, interrupted, superseded |
| Interaction | pending, resolved, rejected, expired |

Ready means there is no active turn. Waiting is durable and nonterminal: it can release the coroutine while preserving the same turn identity. Resolving an interaction resumes the recorded continuation. Restart does not silently launch work.

Every event includes schema_version, event_id, session_id, turn_id, sequence, occurred_at, type, and a validated typed payload. Message events include message_id and delta offset; operation events include operation_id, tool name, attempt, and optional task_id. Session sequence is assigned by one writer. Do not identify concurrent calls by tool name alone.

Minimum events: turn.started/completed/failed/cancelled/interrupted; message.started/delta/completed; operation.started/progress/retrying/completed/failed/cancelled; interaction.requested/resolved; task.updated; evidence.added; context.compacted.

Provider events are a separate typed union: PublicTextDelta, ToolCallDelta, UsageReceived, ModelFinished, ProviderFailure. Raw provider dictionaries stay inside the provider adapter. Tool arguments are provider fragments until fully assembled and schema validated.

Core application methods to implement:

```python
async def submit(session_id: str, text: str) -> str:
    """Return the new turn ID after durably accepting the message."""

async def respond(session_id: str, interaction_id: str, text: str) -> None:
    """Resolve a pending interaction and continue its existing turn."""

async def cancel(session_id: str, turn_id: str) -> None:
    """Cancel owned work, await cleanup, persist outcome."""

async def events(session_id: str, after_sequence: int = 0):
    """Yield typed events for the client; replay durable records as needed."""
```

Completion invariants: no required running operation, no unresolved required interaction, explicit supported outcome, and durable final message. Outcomes are answered, partial, insufficient_evidence, failed, or cancelled. End-of-stream without an outcome is interrupted/failed, not success.

## 5. Conversation and interaction policy

Supported model actions: use registered tool, ask user, propose substantial plan, delegate bounded specialist task, and finish response. Text can precede a tool call; that text is an assistant progress message, not the final answer. A substantive unanswered tool call prevents turn completion.

Guided: ask when ambiguity materially changes scope; confirm substantial research plans. Review: present substantial plans and explicitly requested checkpoints before execution. Autonomous: proceed within agreed scope, but still ask for consequential missing information. All modes use the same capability permissions.

Question payload: interaction_id, kind, prompt, suggested choices, allows_free_text, target_action_id, scope_version. Dynamic clarification questions can be model-generated; the harness validates their structure. Approvals bind to a concrete immutable action/plan digest. Changing that action invalidates its approval.

“Do the full analysis” while a scope question is pending is interpreted against that question and existing objective. A new company, changed timeframe, or contradictory instruction updates the plan rather than being treated as a blanket yes. Destructive permissions require explicit selection rather than fuzzy language interpretation.

The modal supports arrows, Tab, Enter, Y/N where appropriate, details, and free-text revision. Esc dismisses a clarification while keeping it pending; Esc on an approval rejects that action. Outside popups, Esc cancels active work. Ctrl+C cancels active work and exits when idle; application exit awaits cleanup. Preserve native Ctrl+Z suspension where supported rather than advertising it as an exit key.

## 6. Tools and financial evidence

Initial real tools:

| Tool | Existing base / intended implementation |
|---|---|
| resolve_instrument | `app/core/instrument_resolver.py`; exchange-qualified identity |
| search_web | Inspect/reuse `data/news_pipeline/tinyfish_client.py`; validate general search capability separately from news search |
| read_url / read_document | Existing extractor and PyMuPDF; bounded downloads, safe URL/path validation |
| get_prices / get_fundamentals | `data/providers/yfinance.py`; preserve upstream limitations |
| calculate | `quant/` functions with typed input artifacts and recorded parameters |
| run_python | Isolated process/container with explicit input/output mounts and captured artifacts |
| read_project_file | Project-scoped paths; attachment metadata and document sections |
| export_report | Project-local Markdown/JSON artifact, no arbitrary destination overwrite |

Register only callable tools with validated schemas and actual handlers. Tool metadata declares timeout, output limit, side effects, retry safety, and required permissions. Financial context does not imply unrestricted shell access.

Python execution: curated calculations work immediately without arbitrary generated code. Generated Python runs in an OS-enforced restricted environment: no inherited credentials, no network by default, read-only selected inputs, writable run artifact directory, resource limits, subprocess group termination. A working directory or AST filter alone is not a sandbox. If the isolation backend is unavailable, show this capability as unavailable while curated calculations continue to work.

Evidence record: ID, URL/document reference, publisher, retrieval time, publication time where available, effective period, excerpt/page/section, content hash, source category, instrument, currency, units, and extraction warnings. Calculated metric: ID, value, units, input evidence IDs, function/script hash, parameters, software version, as-of time.

Freshness is question-specific. “Latest” triggers retrieval or a freshness-qualified cached result. Historical questions require point-in-time awareness; current fundamentals cannot silently stand in for historical values. Distinguish consolidated/standalone statements, fiscal/calendar periods, adjusted/unadjusted prices, corporate actions, and restatements.

Source existence checks are deterministic. Semantic claim support is assessed separately and remains fallible. Never equate a valid citation ID or an LLM confidence number with verified truth.

## 7. Specialists

Introduce specialists only after the single-agent tool loop works. Reuse financial modules after extracting graph-independent execution functions. A specialist receives an explicit question, scope, relevant artifacts, allowed tools, and a bounded budget. It returns findings, evidence IDs, metric IDs, contradictions, gaps, and outcome.

- Fundamentals: accounting quality, earnings drivers, capital allocation and valuation interpretation.
- Market behavior: interpretation of Python-computed price/volume/risk statistics.
- Macro/sector: relevant exposures and comparable-sector context.
- Events: dated filings, news, catalysts, management communications.
- Counter-thesis/risk: challenge the current evidence and assumptions.

No compulsory five-agent dispatch, recursive spawning, or agent-to-agent messaging network. The parent owns tasks and integrates results. Independent specialists can run concurrently; cancellation propagates to all children. Child context contains selected evidence, not a copy of the entire conversation.

## 8. Storage, context, and memory

Use `.finai/state.sqlite3` for transactional messages, turns, interactions, operations, task state, and durable event records. Use `.finai/artifacts/<session>/<operation>/` for large documents and tool output; `.finai/logs/` for sanitized diagnostics. SQLite earns its place through atomic interaction resolution and operation recovery, using stdlib sqlite3 and a single serialized writer. Do not use a remote database.

Import existing `.finai/sessions/` files once with a versioned migration ledger; preserve originals. Validate session IDs and resolved paths; unknown or ambiguous resume targets must not create new sessions. Sort by actual update timestamp. Handle one malformed legacy record with a reported migration warning rather than hiding the whole session.

Persist accepted user messages before work. Persist operation intent before dispatch and result before the model uses it. Coalesce text deltas into short durable batches, flush on message completion, waiting, cancellation, and exit; document the bounded unflushed-text crash window. Never batch approvals or completed operation results until run end.

On restart mark uncompleted operations interrupted. Retry safe reads only after explicit resume. For side-effecting operations, reconcile saved intent/result and artifact state before any retry. No exactly-once claim for unknown external outcomes.

Working context contains system policy, current objective and accepted decisions, unresolved interactions/tasks, recent complete exchanges, relevant evidence, summaries, and tool-call/result pairs. Retrieved text and summaries remain untrusted content; never promote them into system instructions.

Define usable input budget B = min(configured context cap, verified model context limit) - output reserve - safety margin. Include tool schemas and message overhead. Trigger automatic compaction before a request at >= 0.90 * B. The configured 250K value is not a claim that Hive supports that context size. Unknown provider limits require explicit conservative configuration. Token estimates must be labeled estimates and validated against provider usage when available.

Compaction preserves structured goals, user decisions, unanswered questions, tasks, artifact references, and recent complete tool pairs. Summarize older narrative semantically; verify the new context fits and preserves required IDs before atomically selecting it. Keep original records. `/compact` forces this process even below threshold. A single oversized document is excerpted through artifact reading, never stuffed into context. If compaction fails, retain the prior context and surface a recoverable error.

Cross-session memory is explicit project knowledge: user-confirmed preferences, reusable research notes and their provenance. Do not infer risk tolerance from casual chat, and do not create a vector database until retrieval over local indexed records proves insufficient.

## 9. Terminal behavior

Retain Textual + Rich + asyncio. Textual has worker lifecycle and cancellation support; see [official workers documentation](https://textual.textualize.io/guide/workers/). Domain tasks remain framework-independent.

Use neutral paragraphs, cyan labels, muted metadata, and semantic outcome markers. Remove thick green borders on every answer and repeated green router checklists. Keep the compact startup wordmark only in interactive idle state; reduce to FIN-AI at narrow widths.

```text
You
Compare HDFC Bank with ICICI Bank over the last year.

FIN-AI
I’ll compare performance and fundamentals over that period.

  ✓ Resolved both instruments
  ◉ Retrieving financial statements       8s
    Price history retrieved

────────────────────────────────────────────────────────
> Add a follow-up or refine the scope…
Researching · 1 operation active          Esc cancel
```

One widget per message and one activity group per turn. Tool rows keyed by operation ID support expand/collapse. Streaming updates batch on a timer, initially <=30Hz; flush immediately at message end. This is a proposed refresh setting, not a measured benchmark. Do not add sleeps to manufacture streaming.

Keep composer editable during work. Enter while active offers queue-next-message; draft survives cancellation. Steering is accepted at a controlled boundary, increments scope_version, and cannot silently mutate tools already running. Autoscroll only if the reader was already at the bottom; otherwise show new-content indication.

Slash registry drives completion and help. Implement `/help`, `/new`, `/sessions`, `/resume`, `/history`, `/sources`, `/tools`, `/status`, `/context`, `/compact`, `/mode`, `/model`, `/config`, `/retry`, `/export`, `/debug`, `/logs`, `/clear`, `/exit` only as their supporting services land. `/model` lists configured usable models and capabilities; it does not invent options.

Narrow layout stacks financial labels and preserves complete numeric values. NO_COLOR removes semantic colors but keeps text labels; plain mode has no alternate screen, cursor escapes, or wordmark. Sanitize external ANSI/control sequences; links allow only safe schemes and sanitized destinations. Debug output stays out of chat unless deliberately opened.

## 10. File disposition

| Action | Files |
|---|---|
| Retain and test | `backend/quant/`, `backend/data/providers/yfinance.py`, `backend/data/news_pipeline/`, `backend/app/core/instrument_resolver.py` |
| Refactor provider boundary | `backend/app/services/hive_service.py`, `llm_interface.py`, `backend/app/models/request_models.py` |
| Extend typed contracts | `backend/app/events/models.py`, `backend/app/core/contracts/tool_result.py` |
| Replace top-level control after migration | `backend/app/core/orchestrator.py`, graph router/runtime modules, `backend/finai/stream_adapter.py`, legacy path in `backend/finai/__main__.py` |
| Reuse specialist logic, remove graph-state dependence | `backend/agents/financial/analysis/{fundamental,technical,macro,sentiment,contrarian}.py` |
| Replace persistence internals, retain importer | `backend/finai/session_store.py`, `context_budget.py` moved behind application services |
| Split presentation | `backend/finai/app.py` into composer, transcript, interactions widgets while preserving app entry point |
| Retire after caller migration | `backend/app/core/tools/tool_system.py`, obsolete graph-only prompts/tests, `backend/app/core/model_stream.py` context-local publication bridge |
| Keep API compatibility adapter | `backend/app/routes/chat.py` consumes new events and serializes established wire format |
| Update governance | `ai_engineering/PROJECT_CONSTITUTION.md`, `AGENT_RULES.md`, `SYSTEM_ARCHITECTURE.md`, `ARCHITECTURE_DECISIONS.md` and `AGENTS.md` |

New application files under `backend/app/agent/`: `contracts.py` (actions/state), `runtime.py` (model loop), `controller.py` (session entry points), `tools.py` (registry/runner), `interactions.py` (resolution policy), `sessions.py` (SQLite store/import), `context.py` (assembly/compaction), `evidence.py` (provenance/metrics), `specialists.py` (bounded dispatch), `python_runner.py` (process isolation). Add modules as their milestone lands, not empty scaffolding.

New presentation files: `backend/finai/composer.py`, `transcript.py`, `interactions.py`, `theme.tcss`. Keep existing render and safety helpers where they remain useful. Do not create a second UI state framework.

## 11. Implementation milestones

For every task: write the named regression first, observe its failure where behavior changes, implement, run the targeted tests, review the diff, and checkpoint only its files. Do not stage the entire dirty worktree. Commands below use `PYTHONPATH=backend UV_CACHE_DIR=.uv-cache uv run pytest` as the test prefix.

### M0 — Capture failure and agree on canonical contracts (P0, small)

Files: existing orchestrator/goal tests; new `backend/tests/unit/test_agent_contracts.py`; `backend/app/agent/contracts.py`; governance documents.

- [ ] Add regression with top-level awaiting_approval and string final_output; assert interaction event and absence of run completion. Include clarification variant.
- [ ] Add scripted transcript fixture: greeting → HDFC question → clarification → approval → tool result → cited answer → follow-up.
- [ ] Define versioned contracts and invariants from section 4; document retired mandatory-pipeline assumptions.
- [ ] Patch the existing waiting-state mismatch narrowly so the legacy runtime does not misreport success during migration.

Gate: the screenshot's false-completion case is reproduced and fixed by a deterministic test. No visual-only patch is accepted as evidence.

### M1 — Provider protocol and real tool calls (P0, medium)

Files: Hive service/interface/message models; `backend/tests/unit/test_hive_service.py`; new `test_agent_provider.py`.

- [ ] Assemble fragments by choice/call index and call ID; concatenate argument fragments, validate only when complete.
- [ ] Parse text, usage, tool fragments and finish reason independently, including coexisting fields.
- [ ] Handle length-limit termination as incomplete; reasoning-only output is not a completed public answer.
- [ ] Prevent transparent retry after public output or actionable tool calls have been emitted. Track attempt boundaries explicitly.
- [ ] Return per-request telemetry rather than relying on shared mutable last_telemetry for concurrent calls.
- [ ] Live probe: one deterministic harmless tool function, feed result back, receive final public answer. Record timings/counts without credentials or hidden reasoning.

Gate: interleaved fragmented calls produce exactly one validated invocation each; public deltas arrive before provider completion. If Hive native tool calls are unsupported for the configured model, test a typed action-envelope adapter or explicitly select a capable configured model; do not fabricate support.

### M2 — Durable session controller (P0, medium)

Files: new sessions/controller modules, `backend/finai/session_store.py`, new `test_agent_sessions.py`.

- [ ] Implement SQLite transactions for turn acceptance, pending interactions, operation intent/result, and event sequence assignment.
- [ ] Import existing JSON/JSONL sessions idempotently; preserve originals and report damaged records.
- [ ] Test unknown/prefix-ambiguous/traversal session identifiers, chronological listing and two writers attempting the same session.
- [ ] Test subprocess termination between operation intent/result; restore interrupted state without automatic replay.

Gate: accepted messages and pending questions survive process restart; resume does not create an accidental session. Backend IO is serialized without blocking the terminal event loop.

### M3 — Single conversational agent loop (P0, medium)

Files: runtime/contracts/controller, configuration and focused prompts; new `test_agent_runtime.py`.

- [ ] Implement answer, tool-use, ask-user and finish actions using M1 provider events.
- [ ] Add genuine runtime tool registry with callable handlers; reject unknown tools and schema-invalid arguments before execution.
- [ ] Add cancellation, action/elapsed/concurrency limits, one active turn per session, typed terminal outcomes, and bounded event delivery.
- [ ] Test: definition with no tools; search then answer; tool failure followed by corrected action; premature EOF; repeated identical no-progress requests; cancellation during provider wait.

Gate: a finance conversation chooses work based on context and never enters the legacy graph. No pending tool or interaction can coexist with completed turn state.

### M4 — Finance tools, provenance and Python execution (P1, large; review each tool separately)

Files: tools/evidence/python_runner; existing data/quant modules; new `test_agent_tools.py`, `test_python_runner.py`, `test_agent_evidence.py`.

- [ ] Wrap existing real market/news/quant calls; emit started before invocation and completion/failure after result storage.
- [ ] Add document/URL access with size/time limits, safe redirects, scoped paths and citation references.
- [ ] Bind calculated metrics to source artifacts, parameters, units and calculation version.
- [ ] Add constrained generated Python execution using installed isolation capability; test attempted credential access, network, path escape, runaway output and cancellation of child processes.
- [ ] Implement report export and artifact inspection, with overwrite choices only when a destination exists.

Gate: same inputs reproduce numeric results; concurrent same-name calls retain separate identities; all fetched/calc facts can be traced to artifacts. Unsupported providers are exposed as gaps.

### M5 — Dynamic questions and real continuation (P1, medium)

Files: interactions/controller/runtime, TUI interactions; new `test_agent_interactions.py`.

- [ ] Persist dynamic questions with free text and suggested answers, plus action/scope identity.
- [ ] Resume same turn on answer; test full-analysis wording, timeframe changes, rejection, duplicate response, stale approval and restart while pending.
- [ ] Apply guided/review/autonomous policy without mandatory approval of ordinary reads.
- [ ] Test independent read tasks finishing while a different task waits; derive accurate session status.

Gate: “Proceed” continues recorded work exactly once; changing the proposal cannot reuse the old approval.

### M6 — Context and project memory (P1, medium)

Files: context/sessions/provider capabilities, replace context_budget internals; new `test_agent_context.py`.

- [ ] Compute usable capacity including instructions, tool schemas, output reserve and supplied documents.
- [ ] Implement bounded evidence selection and complete tool-call/result groups.
- [ ] Implement automatic and forced manual compaction, semantic summary plus structured retained state, atomic activation and failure rollback.
- [ ] Test very small configured budgets, one oversized document, repeated compaction, restarted compacted session, inaccurate tokenizer estimates and pending interactions.
- [ ] Add inspect/edit/delete commands for explicit project memory only after durable schema exists.

Gate: post-compaction context fits the budget and retains specified goals/decisions/evidence/task references; original session remains available.

### M7 — Terminal and plain client migration (P1, medium)

Files: finai app/composer/transcript/interactions/render/commands/plain/__main__; new/updated terminal tests.

- [ ] Connect submit/respond/cancel/events methods; remove runtime ownership from widgets.
- [ ] Render separate message IDs, operation groups, interaction modal and accurate current activity; strip synthetic tool milestones.
- [ ] Implement timer-batched public text rendering and incremental one-shot plain/JSON writing.
- [ ] Add session browser with preview and restored transcript/pending question; searchable command suggestions, input history and multiline paste.
- [ ] Preserve reading position and drafts; queue additional input explicitly; await cleanup on exit.
- [ ] Test intermediate rendered text while fake provider is held open, concurrent tools, modal keys, 40/80/140 columns, resize, NO_COLOR and 500 messages.

Gate: no text loss/duplication, no false running/completed labels, no UI task orphaned after cancellation. Manual VS Code/Linux validation recorded separately from headless tests.

### M8 — Focused specialist delegation (P2, medium)

Files: specialists and existing analysis modules; new `test_agent_specialists.py`.

- [ ] Extract callable financial analysis logic from graph nodes without rewriting working calculations.
- [ ] Add bounded per-specialist instructions, selected context and tools; parent owns all delegation.
- [ ] Test dependency ordering, independent parallel work, conflicting findings, source gaps and parent cancellation.
- [ ] Compare single-agent versus specialist-assisted results on frozen investigations before enabling automatic delegation broadly.

Gate: delegation improves a measured subset or remains explicit/on-demand. More model calls alone are not a quality gain.

### M9 — Research quality, cutover and retirement (P0 release gate, large)

Files: `evals/run.py`, `evals/metrics.py`, gold manifests/tasks, docs, existing API route, pyproject and lockfile only after dependency cleanup.

- [ ] Add frozen cases for definitions, current facts, HDFC/ICICI comparison, merger comparability, contradictory sources, missing data, cancellation, resumed approvals, compaction and script calculations.
- [ ] Separate deterministic fixture tests, source-support review, optional live provider tests and manual terminal tests.
- [ ] Track citation support, numerical provenance, task completion, correct clarification decisions, false completion, tool error recovery and response latency. No cost dashboard.
- [ ] Run complete offline backend suite to termination; isolate/mark tests that actually require live services. Diagnose the previously slow integration test rather than increasing timeouts blindly.
- [ ] Switch CLI and API to the shared runtime. Confirm feature parity for still-supported endpoints and sessions.
- [ ] Remove legacy graph routing, adapters, unused prompts and tool stubs only after import/caller search, regression pass and session import verification. Remove LangGraph only if no retained consumer needs it.

Gate: all P0 invariants pass; no fabricated sources/metrics in deterministic cases; live and manual evidence documented without presenting them as guaranteed model quality.

## 12. Execution order and review boundaries

M0 → M1 → M2 → M3 is the first vertical slice. Then M4 and M5 deliver a usable research assistant; M6 and M7 make it durable and comfortable. M8 adds specialists after the base agent is dependable. M9 gates release and deletion.

Provider protocol tests and persistence tests can be developed independently after contracts are agreed. Avoid simultaneous edits to shared runtime/controller contracts. Review milestones against user-visible behavior, not the number of modules created.

First demo acceptance transcript:

1. Hello → brief answer, no research/tool checklist.
2. Explain bank net interest margin → conversational explanation.
3. Compare HDFC Bank and ICICI Bank over one year → resolve instruments and scope; real retrieval/calculation activity.
4. Change the comparison period → retain objective and revise affected work.
5. Challenge the conclusion → targeted counter-evidence, not a repeated full pipeline.
6. Close while awaiting input → reopen exact pending question.
7. Cancel running retrieval → return to usable composer and retain partial work.

## 13. Verification commands and honest evidence

```sh
PYTHONPATH=backend UV_CACHE_DIR=.uv-cache uv run pytest -q backend/tests/unit/test_agent_contracts.py
PYTHONPATH=backend UV_CACHE_DIR=.uv-cache uv run pytest -q backend/tests/unit/test_agent_provider.py
PYTHONPATH=backend UV_CACHE_DIR=.uv-cache uv run pytest -q backend/tests/unit/test_agent_sessions.py backend/tests/unit/test_agent_runtime.py
PYTHONPATH=backend UV_CACHE_DIR=.uv-cache uv run pytest -q backend/tests
UV_CACHE_DIR=.uv-cache uv run ruff check backend
UV_CACHE_DIR=.uv-cache uv run mypy backend/app/agent backend/finai
```

New test paths above are deliverables, not currently runnable claims. For modified boundaries, use deterministic fake provider streams to assert intermediate state before completion. Provider integration then verifies real native tool execution and timing. Manual terminal checks cover focus, scrolling, pasting, resize, cancellation, exit restoration and restart in the actual VS Code terminal.

Proposed performance targets to measure: local submit acknowledgment within 200ms under normal load, <=30 render updates/sec while streaming, no dropped text across 1,000 deltas, and responsive input with 500 transcript messages. These are release targets, not achieved benchmarks; record hardware and input size.

## 14. Principal risks and decisions

- Model capability: public SSE support does not imply correct native tool calling. M1 is a blocking gate for runtime design.
- Research truth: citation syntax checking cannot establish semantic support; manual/source-based evaluation remains necessary.
- Streaming validation: public narrative can be provisional while generated. Stream from already checked evidence/metrics, validate completion, and publish an explicit correction if final checking rejects a claim. Do not silently claim prevalidated prose while exposing unchecked tokens.
- Recovery: arbitrary scripts and external effects cannot be blindly replayed; preserve indeterminate outcomes.
- Broad access: generated Python requires real isolation. No fake sandbox to meet a feature checklist.
- Complexity: avoid vector memory, recursive agents, distributed queues, and graph-framework replacement dependencies until a measured need arises.
- Governance drift: current rules say all agents return JSON and refer to obsolete model arrangements. Update them to distinguish typed specialist/tool outputs from public conversational messages.

The release objective is a reliable conversational finance assistant. “Best” or “hedge-fund level” requires comparative evidence on research quality and reliability; neither is asserted by this implementation plan.

## References

- [Textual workers](https://textual.textualize.io/guide/workers/): asynchronous UI work, worker lifecycle and cancellation.
- [Hive chat completions](https://docs.thehive.ai/docs/chat-completions-openai-compatible-llms): provider protocol reference; configured model behavior must still be tested.
- Current repository files in section 2 and user-approved product requirements in this conversation are the primary design inputs.
