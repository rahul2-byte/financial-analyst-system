# Institutional Research Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Evolve the current AgentLoop-based FIN-AI CLI into a reproducible, evidence-governed financial research platform without adding complexity that is not justified by a measured failure.

**Architecture:** Keep one process and one canonical AgentLoop workflow. Add explicit contracts around provider data, deterministic calculations, structured findings, publication, risk, and evaluation. LLMs synthesize and explain validated results; they do not calculate, fetch infrastructure directly, or override policy.

**Tech Stack:** Python 3.11+, Pydantic v2, asyncio, existing Textual/Rich CLI, existing providers and quant modules, JSONL/local artifacts first; add persistent services only when workload evidence requires them.

**Spec:** `docs/architecture/current-state.md` plus the approved P99 architecture specification in the implementation request.

## Global Constraints

- Preserve the AgentLoop as the canonical runtime.
- LLMs must never calculate financial values, ratios, indicators, forecasts, scores, or risk limits.
- Every external dataset must expose source, dataset, instrument, observation time, ingestion time, version, and quality status.
- Invalid or insufficient evidence must fail closed or produce an explicitly partial report.
- Agents communicate through typed structures and do not call other agents directly.
- Prefer existing dependencies and local artifacts before adding infrastructure.
- Keep all changes incremental, typed, observable, and independently testable.
- A phase is complete only after its focused tests, full backend tests, Ruff, and mypy pass.

## Current baseline

Already implemented and verified: AgentLoop runtime, explicit ticker/cache isolation, provider provenance envelopes, basic publication evidence gating, structured provenance/claim validators, local event ledger, and a seeded synthetic evaluation set. The synthetic benchmark is not evidence of live-market accuracy.

## Dependency order

```text
1 Data contract
  -> 2 Publication contract
  -> 3 Quant contract
  -> 4 Research artifacts
  -> 5 Typed tools
  -> 6 Agents
  -> 7 Orchestration
  -> 8 Signals
  -> 9 Risk
  -> 10 Evaluation
  -> 11 Observability
  -> 12 Security/governance
  -> 13 Infrastructure scaling
  -> 14 Documentation and release review
```

---

### Task 1: Complete the data-quality and provenance platform

**Files:**
- Modify: `backend/app/core/research_schemas.py`
- Modify: `backend/app/core/agent_loop/runtime.py`
- Modify: `backend/data/providers/yfinance.py`
- Create: `backend/data/quality.py`
- Test: `backend/tests/unit/test_data_quality.py`
- Test: `backend/tests/unit/test_registry_tool_runner.py`

**Interfaces:**
- Produce `DataQualityStatus`, `DataQualityIssue`, and `validate_market_records(records, instrument, observed_at) -> tuple[DataQualityIssue, ...]`.
- Provider adapters return `ProviderEnvelope[T]` containing `data`, `provenance`, and `quality_issues`.
- Downstream code consumes only envelopes with no blocking quality issues.

- [ ] Add failing tests for duplicate timestamps, missing required OHLCV fields, non-UTC timestamps, non-positive prices, and instrument mismatch.
- [ ] Implement the validator with deterministic issue codes: `MISSING_FIELD`, `DUPLICATE_TIMESTAMP`, `INVALID_TIMEZONE`, `INVALID_PRICE`, and `INSTRUMENT_MISMATCH`.
- [ ] Add explicit adjustment policy and provider retrieval timestamp to market output.
- [ ] Mark current `Ticker.info` fundamentals as `degraded` because they are current snapshots, not point-in-time history.
- [ ] Preserve raw provider payloads under the existing session artifact directory with a content hash.
- [ ] Verify focused tests, then `UV_CACHE_DIR=.uv-cache uv run pytest backend/tests -q`, Ruff, and mypy.

**Exit criteria:** No provider result reaches quant code without a validated envelope; invalid data is represented as a structured failure.

### Task 2: Make publication validation enforceable for generated reports

**Files:**
- Modify: `backend/app/core/research_schemas.py`
- Modify: `backend/app/core/research_quality.py`
- Modify: `backend/app/core/agent_loop/runtime.py`
- Modify: `backend/finai/session.py`
- Create: `backend/app/core/publication.py`
- Test: `backend/tests/unit/test_publication.py`
- Test: `backend/tests/unit/test_agent_loop.py`

**Interfaces:**
- Add `ReportClaim` with `claim_id`, `text`, `importance`, `evidence_refs`, `numeric_fields`, and `status`.
- Add `PublicationDecision(status: Literal["publish", "partial", "withhold"], reasons, claims)`.
- Implement `evaluate_publication(report, evidence) -> PublicationDecision`.

- [ ] Add failing tests for an unsupported major claim, unknown evidence ID, contradicted claim, and unsupported numeric field.
- [ ] Define a structured report envelope that separates facts, calculations, interpretation, risks, limitations, and citations.
- [ ] Validate claim references and numeric values against deterministic evidence before persistence as a completed report.
- [ ] Downgrade free-form model output to `partial` when it cannot be represented as a valid structured report; never silently mark it fully published.
- [ ] Emit the decision and reasons as typed events and render them in plain/JSON/TUI interfaces.
- [ ] Verify focused tests plus full suite, Ruff, and mypy.

**Exit criteria:** A model response cannot become a completed report without passing the publication decision.

### Task 3: Formalize deterministic financial and quantitative services

**Files:**
- Modify: `backend/quant/indicators.py`
- Modify: `backend/quant/fundamentals.py`
- Modify: `backend/quant/validators.py`
- Create: `backend/quant/contracts.py`
- Test: `backend/tests/quant/`

**Interfaces:**
- Define immutable `CalculationInput` and `CalculationOutput` with instrument, window, dataset version, formula version, values, and warnings.
- Quant functions accept validated records, not arbitrary model payloads.

- [ ] Characterize current return, RSI, MACD, moving-average, volatility, and fundamental calculations.
- [ ] Add explicit window, interval, price-adjustment, and insufficient-observation behavior.
- [ ] Add property tests for monotonic prices, constant prices, missing values, duplicate timestamps, and split-adjusted data.
- [ ] Include formula/version metadata in every calculation output.
- [ ] Remove any calculation path that accepts unvalidated model-supplied arrays.
- [ ] Verify quant tests, full suite, Ruff, and mypy.

**Exit criteria:** Every published number is produced by a versioned deterministic calculation or is explicitly labeled as a provider observation.

### Task 4: Add reproducible research artifacts and experiment lifecycle

**Files:**
- Create: `backend/research/models.py`
- Create: `backend/research/artifacts.py`
- Create: `backend/research/experiments.py`
- Modify: `backend/finai/session_store.py`
- Test: `backend/tests/unit/test_research_artifacts.py`

**Interfaces:**
- `ExperimentManifest(experiment_id, dataset_versions, feature_version, configuration_hash, code_version, prompt_version, model_id, created_at)`.
- `ResearchArtifact(kind, path, sha256, media_type)`.
- `save_experiment(manifest, artifacts) -> Path` and `load_experiment(experiment_id) -> ExperimentManifest`.

- [ ] Add failing tests for deterministic manifest hashes, missing artifacts, and corrupted artifact hashes.
- [ ] Persist manifests and artifact references atomically beside existing session runs.
- [ ] Record configuration, code identity, prompt/skill hashes, and provider evidence references.
- [ ] Add replay loading that never calls live providers.
- [ ] Verify artifact tests, full suite, Ruff, and mypy.

**Exit criteria:** A historical run can be inspected and deterministic stages can be replayed from retained inputs.

### Task 5: Replace loose tool boundaries with typed tool contracts

**Files:**
- Modify: `backend/app/core/tools/tool_catalog.py`
- Modify: `backend/app/core/tools/tool_handlers.py`
- Modify: `backend/app/core/agent_loop/runtime.py`
- Create: `backend/app/core/tools/contracts.py`
- Test: `backend/tests/unit/test_tool_contracts.py`

**Interfaces:**
- `ToolSpec[InputModel, OutputModel]` with name, permission, timeout, retry policy, and schema.
- `ToolExecutionContext(run_id, instrument, deadline, evidence_ids)`.
- `ToolResult[OutputModel]` with status, output, provenance, and error code.

- [ ] Add contract tests for malformed arguments, unknown tools, timeout, retryable provider errors, and permission denial.
- [ ] Convert market, fundamentals, news, and quant tools to typed input/output models.
- [ ] Keep submission/delegation tools out of the model-facing catalog unless explicitly required by a workflow.
- [ ] Verify focused tests plus full suite, Ruff, and mypy.

**Exit criteria:** Agents cannot access provider internals or pass untyped financial arrays through the tool boundary.

### Task 6: Keep only reasoning-bearing agents and formalize their contracts

**Files:**
- Modify: `backend/agents/financial/analysis/*.py`
- Modify: `backend/agents/base.py`
- Create: `backend/agents/contracts.py`
- Test: `backend/tests/unit/test_agent_contracts.py`

**Interfaces:**
- `AgentRequest(context: ResearchContext, evidence: tuple[EvidenceRecord, ...])`.
- `AgentResponse(status, findings, claims, risks, missing_evidence, confidence)`.
- Agents remain single-purpose: retrieval/context, fundamental interpretation, technical interpretation, news/sentiment classification, synthesis, and validation.

- [ ] Add contract tests for malformed output, missing evidence, confidence bounds, and forbidden numeric computation.
- [ ] Move deterministic work out of agent modules into `backend/quant` or `backend/data`.
- [ ] Define forbidden actions per agent; no agent may invoke another agent or mutate persistence.
- [ ] Keep specialist-agent count bounded until evaluation demonstrates a missing capability.
- [ ] Verify agent tests, full suite, Ruff, and mypy.

**Exit criteria:** Every agent has one responsibility, typed input/output, explicit failure behavior, and no hidden side effects.

### Task 7: Harden orchestration and partial-failure behavior

**Files:**
- Modify: `backend/app/core/agent_loop/runtime.py`
- Modify: `backend/finai/supervisor.py`
- Create: `backend/app/core/workflows/research_workflow.py`
- Test: `backend/tests/unit/test_research_workflow.py`
- Test: `backend/tests/integration/test_failure_recovery.py`

**Interfaces:**
- `WorkflowState` transitions: `created -> running -> awaiting_input -> partial|completed|failed|cancelled`.
- `WorkflowPolicy` defines per-stage deadline, retry count, and allowed tools.
- `execute_workflow(request, policy) -> AsyncIterator[ResearchEvent]`.

- [ ] Add failing tests for timeout, cancellation, duplicate tool event, retry exhaustion, provider outage, and one failed parallel branch.
- [ ] Implement bounded parallel evidence acquisition with per-stage deadlines and idempotency keys.
- [ ] Classify errors as retryable, non-retryable, user-actionable, or internal.
- [ ] Preserve successful branches and publish partial results with explicit missing evidence.
- [ ] Add recovery from checkpoints without re-running completed tool calls.
- [ ] Verify integration tests plus full suite, Ruff, and mypy.

**Exit criteria:** Provider or agent failure produces a deterministic terminal state and never leaves an ambiguous successful run.

### Task 8: Add a formal signal representation and combination pipeline

**Files:**
- Create: `backend/signals/models.py`
- Create: `backend/signals/normalization.py`
- Create: `backend/signals/ensemble.py`
- Test: `backend/tests/unit/test_signals.py`

**Interfaces:**
- Frozen `Signal(symbol, timestamp, value, confidence, source, horizon, version, evidence_ids)`.
- `normalize_signals(signals) -> tuple[Signal, ...]`.
- `combine_signals(signals, method="confidence_weighted") -> Signal`.

- [ ] Add tests for bounds, duplicate sources, missing confidence, conflicting directions, and zero-signal input.
- [ ] Implement bounded normalization and confidence-weighted aggregation with deterministic tie handling.
- [ ] Record source and evidence IDs for every combined signal.
- [ ] Keep regime-conditioned weighting out until a benchmark demonstrates regime instability.
- [ ] Verify focused tests, full suite, Ruff, and mypy.

**Exit criteria:** Signals are typed, traceable, normalized, and cannot be combined through ad hoc model prose.

### Task 9: Implement an independent deterministic risk engine

**Files:**
- Create: `backend/risk/models.py`
- Create: `backend/risk/engine.py`
- Test: `backend/tests/unit/test_risk_engine.py`

**Interfaces:**
- `ProposedPosition(symbol, quantity, price, sector, liquidity, timestamp)`.
- `RiskLimits(gross, net, symbol, sector, concentration, volatility, drawdown)`.
- `RiskDecision(action: Literal["approve", "resize", "reject"], quantity, reasons, metrics)`.
- `evaluate_position(position, portfolio, limits) -> RiskDecision`.

- [ ] Add tests for each limit, combined breaches, missing prices, stale data, and kill-switch activation.
- [ ] Implement deterministic approve/resize/reject decisions with auditable reason codes.
- [ ] Make risk inputs immutable and reject stale or unvalidated values.
- [ ] Ensure no agent/tool path can override risk decisions.
- [ ] Verify risk tests, full suite, Ruff, and mypy.

**Exit criteria:** Risk controls are independent, deterministic, auditable, and not reachable through LLM override instructions.

### Task 10: Expand evaluation from seeded fixtures to permitted frozen evidence

**Files:**
- Modify: `evals/metrics.py`
- Modify: `evals/run.py`
- Modify: `evals/gold/v1/tasks.jsonl`
- Modify: `evals/gold/v1/source-manifest.json`
- Create: `evals/gold/v2/`
- Test: `backend/tests/unit/test_evaluation_metrics.py`

**Interfaces:**
- `GoldCase` includes query, frozen evidence IDs, expected facts/tolerances, required citations, risks, forbidden claims, and expected terminal status.
- `EvaluationReport` includes completeness, provenance, claim support, citation, safety, latency, cost, and failure metrics.

- [ ] Keep v1 synthetic fixtures as contract tests and label them accordingly.
- [ ] Add a v2 manifest only from permitted, frozen public snapshots with hashes and human-authored labels.
- [ ] Add adversarial cases for stale data, wrong instrument, unsupported historical claims, provider disagreement, and partial evidence.
- [ ] Add regression thresholds that fail CI when critical metrics regress.
- [ ] Separate offline benchmark results from live provider diagnostics.
- [ ] Verify evaluation tests, a complete offline run, full suite, Ruff, and mypy.

**Exit criteria:** The project can measure improvement without treating synthetic fixtures or live smoke tests as market-quality proof.

### Task 11: Complete observability and exact run manifests

**Files:**
- Modify: `backend/app/events/models.py`
- Modify: `backend/app/events/ledger.py`
- Modify: `backend/app/core/diagnostics.py`
- Create: `backend/app/observability/run_manifest.py`
- Test: `backend/tests/unit/test_run_manifest.py`

**Interfaces:**
- `RunManifest` captures query, workflow, code, prompt, model, tools, evidence, calculations, publication decision, latency, token usage, cost, and errors.
- `record_manifest(manifest) -> Path` and `load_manifest(run_id) -> RunManifest`.

- [ ] Add tests for redaction, large-payload artifact storage, torn-tail recovery, and deterministic manifest hashing.
- [ ] Add typed events for evidence accepted/rejected, calculation completed, claim validated, and publication decided.
- [ ] Keep payload logging bounded and redact secrets by default.
- [ ] Add stage latency and provider failure summaries without logging private chain-of-thought.
- [ ] Verify observability tests, full suite, Ruff, and mypy.

**Exit criteria:** Every completed or failed run has an inspectable manifest sufficient to explain and replay deterministic stages.

### Task 12: Add security and governance controls

**Files:**
- Modify: `backend/app/config/models.py`
- Modify: `backend/app/core/tools/contracts.py`
- Create: `backend/app/security/policy.py`
- Create: `backend/app/security/redaction.py`
- Test: `backend/tests/unit/test_security_policy.py`

**Interfaces:**
- `Permission(subject, action, resource)` and `authorize(context, permission) -> bool`.
- `redact_sensitive(value) -> value`.
- `DataLicense(source, permitted_use, expires_at, redistribution_allowed)`.

- [ ] Add tests for missing secrets, unauthorized tool access, path traversal, sensitive-log redaction, and expired data permission.
- [ ] Apply least-privilege permissions to tools and filesystem access.
- [ ] Centralize secret loading through settings; never persist API keys in artifacts.
- [ ] Record source-license metadata alongside evidence manifests.
- [ ] Verify security tests, full suite, Ruff, and mypy.

**Exit criteria:** External access, secrets, logs, and data rights have explicit boundaries and audit records.

### Task 13: Introduce infrastructure only where measured workload requires it

**Files:**
- Create: `docs/architecture/deployment-levels.md`
- Modify: `backend/app/config/paths.py`
- Modify: `backend/app/events/ledger.py` only if concurrent persistence is demonstrated
- Test: `backend/tests/integration/test_storage_recovery.py`

**Interfaces:**
- `StorageBackend` remains a small protocol: `write_artifact`, `read_artifact`, `exists`, and `delete_expired`.
- Local filesystem is the default implementation; PostgreSQL/object storage is an optional later implementation behind the same boundary.

- [ ] Measure current run size, concurrency, latency, and recovery requirements before adding services.
- [ ] Add storage recovery tests for interrupted writes, corrupted artifacts, and retention cleanup.
- [ ] Keep local JSONL for single-user operation; introduce a database only when concurrent users or query requirements justify it.
- [ ] Document deployment levels from local research to multi-user production; explicitly defer Kafka/Kubernetes/vector databases/HFT execution.
- [ ] Verify integration tests, full suite, Ruff, and mypy.

**Exit criteria:** Infrastructure complexity is justified by measured requirements and remains replaceable.

### Task 14: Documentation, release gates, and final architecture review

**Files:**
- Modify: `docs/architecture/current-state.md`
- Create: `docs/architecture/target-state.md`
- Create: `docs/runbooks/research-failure.md`
- Modify: `README.md`
- Test: `backend/tests/integration/test_cli_smoke.py`

**Interfaces:**
- Document the canonical command, workflow states, evidence/report contracts, artifact locations, and validation commands.
- Release checklist must require tests, Ruff, mypy, offline evaluation, and CLI smoke validation.

- [ ] Update architecture diagrams to match the actual AgentLoop path and remove obsolete graph terminology.
- [ ] Document where a developer changes providers, quant logic, tools, prompts, agents, risk, and evaluation cases.
- [ ] Add a failure runbook covering missing API keys, provider outages, invalid evidence, stale data, and recovery.
- [ ] Add a CLI smoke test using deterministic fakes; keep live-provider checks separate and clearly labeled.
- [ ] Run the complete verification matrix and review every introduced abstraction for deletion or simplification.

**Exit criteria:** A new engineer can trace execution, reproduce a run, understand ownership, and verify a release without relying on tribal knowledge.

## Final verification matrix

```text
UV_CACHE_DIR=.uv-cache uv run pytest backend/tests -q
UV_CACHE_DIR=.uv-cache uv run ruff check backend evals docs
UV_CACHE_DIR=.uv-cache uv run mypy backend
UV_CACHE_DIR=.uv-cache uv run python evals/run.py ... --mode offline
UV_CACHE_DIR=.uv-cache uv run python -m finai --plain ...   # deterministic fake-provider smoke test
```

Do not claim P99 quality from passing tests alone. Promote a maturity level only when its exit criteria, frozen evidence evaluation, operational measurements, and governance requirements are satisfied.
