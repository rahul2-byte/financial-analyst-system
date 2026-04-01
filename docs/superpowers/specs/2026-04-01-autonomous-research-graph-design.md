# Autonomous Multi-Agent Research Graph (Replacement Design)

## 1) Objective and Scope

This design replaces the current primary orchestration flow with a fully autonomous, state-driven, production-grade multi-agent research system for financial/trading analysis.

The design enforces:

- no hallucinated data usage,
- deterministic control logic,
- structured JSON outputs from all agents,
- iterative critic/reflection loops,
- graceful handling of partial data and failures,
- strict bounded execution (`MAX_ITERATIONS = 8`, `RETRY_LIMIT = 3`).

Out of scope:

- direct trade execution,
- LLM-based numeric computation,
- unstructured agent responses.

## 2) Non-Negotiable Invariants

1. Every agent returns structured JSON and includes:
   - `reasoning: string`
   - `confidence_score: float (0.0 to 1.0)`
   - `next_action: string`
2. If required data for a claim is unavailable and cannot be fetched within retry policy, the system emits `INSUFFICIENT DATA` for that claim/domain.
3. Router decisions are state-driven only (no hardcoded linear workflow assumptions).
4. Quantitative computations remain deterministic Python logic in `backend/quant/` or deterministic validators.
5. Execution is bounded by:
   - `MAX_ITERATIONS = 8`
   - `RETRY_LIMIT = 3`
   - `CONFIDENCE_THRESHOLD = 0.75`

## 3) Target File-Level Architecture (Replacement)

### Core orchestration files (replace)

- `backend/app/core/graph/graph_state.py`
  - Replace with strict typed state schema for autonomous loop.
- `backend/app/core/graph/graph_builder.py`
  - Replace with central router-driven LangGraph topology.
- `backend/app/core/graph/research_graph.py`
  - Replace with subgraph composition for research execution and loop controls.

### New node modules (add)

- `backend/app/core/graph/nodes/router_node.py`
- `backend/app/core/graph/nodes/goal_hypothesis_node.py`
- `backend/app/core/graph/nodes/data_checker_node.py`
- `backend/app/core/graph/nodes/data_planner_node.py`
- `backend/app/core/graph/nodes/data_fetch_node.py`
- `backend/app/core/graph/nodes/research_planner_node.py`
- `backend/app/core/graph/nodes/exec_fundamental_node.py`
- `backend/app/core/graph/nodes/exec_sentiment_node.py`
- `backend/app/core/graph/nodes/exec_macro_node.py`
- `backend/app/core/graph/nodes/synthesis_node.py` (replace internals; keep path)
- `backend/app/core/graph/nodes/critic_node.py`
- `backend/app/core/graph/nodes/reflection_node.py`
- `backend/app/core/graph/nodes/conflict_resolution_node.py`
- `backend/app/core/graph/nodes/validation_node.py` (replace internals; keep path)

### Prompt definitions (add/update)

- `backend/config/prompts/autonomous_orchestrator.yaml`
  - prompt sections for all autonomous agents above.

### Test suite (add/update)

- `backend/tests/unit/test_autonomous_graph_state.py`
- `backend/tests/unit/test_autonomous_router.py`
- `backend/tests/unit/test_autonomous_loops.py`
- `backend/tests/unit/test_autonomous_critic_reflection.py`
- `backend/tests/unit/test_autonomous_conflict_resolution.py`
- `backend/tests/unit/test_autonomous_validation.py`

### Dead code removal policy

- Remove obsolete graph routing code paths, stale node mappings, and tests tied exclusively to the retired flow.
- Ensure no import references remain to retired orchestration routes.

## 4) State Schema (Mandatory)

`AutonomousResearchState` (TypedDict/Pydantic-compatible transport):

- `request_id: str`
- `user_query: str`
- `goal: dict | None`
  - `{objective, scope, constraints, success_criteria}`
- `hypotheses: list[dict]`
  - each `{id, statement, rationale, priority}`
- `data_status: dict`
  - keys: `ohlcv`, `news`, `fundamentals`, `macro`
  - each `{available, partial, freshness, source, coverage, error}`
- `data_plan: list[dict]`
  - ordered fetch actions with priority
- `tasks: list[dict]`
  - research tasks with dependencies, required datasets, and scheduling priority
  - each `{task_id, agent, required_datasets, dependencies, priority, estimated_cost, cache_key}`
  - `priority` enum: `P0 | P1 | P2 | P3` (`P0` highest)
  - deterministic tie-breakers for ready tasks: `estimated_cost ASC`, then `task_id ASC`
- `results: dict`
  - `fundamental`, `sentiment`, `macro`, `synthesis`, `critic`, `reflection`, `conflict_resolution`, `validation`
- `confidence_score: float`
  - single routing source-of-truth; always mirrors `smoothed_confidence`
- `synthesis_confidence: float`
  - raw confidence emitted by synthesis before critic adjustment
- `adjusted_confidence: float`
  - post-critic penalty confidence used for stabilization inputs
- `final_confidence: float`
  - post-validation confidence used in final response
- `confidence_history: list[float]`
  - bounded rolling window of adjusted confidence values
- `smoothed_confidence: float`
  - moving average over `confidence_history` (window size `N=3`)
- `confidence_components: dict`
  - `{evidence_strength, data_completeness, contradiction_penalty, hallucination_penalty, freshness_penalty, weak_evidence_penalty}`
- `critic_decision: str | None`
  - one of `approve | retry | conflict | insufficient_data`
- `router_decision: str | None`
- `iteration_count: int`
- `retry_count: dict`
  - keyed per domain/node: `{data_fetch, research, synthesis, critic, validation, ...}`
- `freshness_policy: dict`
  - dataset recency thresholds, penalties, and refetch triggers
- `evidence_strength: float`
  - deterministic aggregate evidence quality score in `[0.0, 1.0]`
- `execution_budget: dict`
  - budget and cost tracking for routing optimization (`token_cost`, `tool_cost`, `time_cost`)
- `timeouts: dict`
  - deterministic async controls `{task_timeout_s, stage_timeout_s, cancel_grace_s}`
- `errors: list[dict]`
  - structured errors with `{node, code, message, retryable}`
- `history: list[dict]`
  - append-only decision trace
- `termination_reason: str | None`
- `final_output: dict | None`

Merge semantics:

- append for `history`/`errors`,
- replace for scalar control fields,
- deep-merge for `results` and `data_status`.

Confidence authority rule:

- `confidence_score` is the only authoritative routing confidence.
- `confidence_score` is set only by router as `smoothed_confidence` after critic pass.
- Node-level confidence values (`synthesis_confidence`, agent confidences) are inputs, never direct routing gates.
- `final_confidence` is publication metadata only and must not drive router transitions.

## 5) Agent Contracts (JSON Only)

All agent nodes return a common envelope:

```json
{
  "status": "success | failure | partial",
  "reasoning": "string",
  "confidence_score": 0.0,
  "next_action": "string",
  "data": {},
  "errors": []
}
```

Agent-specific payloads in `data`:

1. Goal + Hypothesis Agent
   - `goal`, `hypotheses`
2. Data Checker Agent
   - `data_status`
3. Data Planner Agent
   - `data_plan` with priorities, fallbacks, and cost estimates
4. Data Fetch Layer
   - fetched dataset artifacts + fetch metadata
5. Research Planner Agent
   - `tasks` and execution ordering by `priority` then dependency readiness
6. Fundamental/Sentiment/Macro Agents
   - domain findings, evidence refs, signal direction
7. Synthesis Agent
   - confidence-weighted integrated view + unresolved gaps
8. Critic Agent
   - `decision` (`approve|retry|conflict|insufficient_data`), issue list
   - must emit evidence quality findings and stale-data penalties
9. Reflection Agent
   - failure diagnosis + concrete improvements
10. Conflict Resolution Agent
   - reconciled signal set + arbitration rationale
11. Validation Agent
   - final pass/fail sanity and release readiness

## 6) Router-Centric Control Logic

Router is the central decision node and the only node that chooses the next stage.

Inputs to router decision:

- current `state` (data availability, errors, retries, iteration budget),
- authoritative `confidence_score` (smoothed post-critic confidence),
- latest `critic_decision`,
- unresolved conflicts and validation status,
- freshness threshold violations,
- evidence strength threshold status,
- node execution cost/budget and cached result availability.

Router decision outputs (`router_decision`):

- `run_goal_hypothesis`
- `run_data_check`
- `run_data_plan`
- `run_data_fetch`
- `run_research_plan`
- `run_research_exec`
- `run_synthesis`
- `run_critic`
- `run_reflection`
- `run_conflict_resolution`
- `run_validation`
- `terminate_success`
- `terminate_insufficient_data`
- `terminate_budget_exceeded`
- `terminate_failure`

Deterministic policy examples:

- If essential dataset for active hypothesis is missing and fetch retries available -> `run_data_fetch`.
- If any required dataset freshness is below threshold and data fetch retries remain -> `run_data_fetch` before research rerun.
- If critic says `conflict` -> `run_conflict_resolution`.
- If critic says `retry` and retry budget remains -> `run_reflection` then `run_research_plan`.
- If `evidence_strength < EVIDENCE_STRENGTH_THRESHOLD` -> force `run_reflection`/`run_research_plan` (never terminate success).
- If `confidence_score >= 0.75` and critic `approve` and validation pass -> `terminate_success`.
- If iteration/retry budgets exceeded -> graceful termination with best available evidence and explicit insufficiency markers.

Cost-aware routing optimization:

- Prefer reusing cached node outputs when input hash is unchanged.
- Prefer cheaper deterministic nodes before expensive LLM nodes when both can satisfy next information need.
- Avoid re-running successful expensive nodes unless critic/reflection identifies direct dependency invalidation.
- Use `execution_budget` to short-circuit non-critical reruns under budget pressure.

## 7) Required Autonomous Loops

### 7.1 Data loop

`data_checker -> data_planner -> data_fetch -> data_checker`

- Stops when data is sufficient or fetch budget exhausted.
- Supports partial availability by marking coverage and confidence penalties.
- Applies freshness policy:
  - stale data incurs `freshness_penalty`,
  - hard-stale data triggers mandatory refetch attempt before approval path.

### 7.2 Research loop

`research_planner -> parallel_exec_agents -> synthesis -> critic`

- If low confidence / weak evidence -> reflection-guided replan and rerun.
- Task scheduler executes highest-priority ready tasks first; lower-priority tasks may be skipped under budget pressure if confidence target can still be met.

### 7.3 Critic-reflection loop

`critic -> reflection -> router`

- Reflection proposes concrete improvements (task reprioritization, alternate data source, narrower claim scope).

### 7.4 Conflict loop (explicit)

`critic(conflict) -> conflict_resolution -> synthesis -> critic`

- This loop is mandatory whenever `critic_decision == conflict`.
- Router must not bypass re-synthesis or re-critic after conflict resolution.
- Loop exits only on `approve`, `retry` (non-conflict), insufficiency, or budget termination.

## 8) Parallel Research Execution

Execution node fan-out runs:

- Fundamental analysis,
- Sentiment analysis,
- Macro analysis

in parallel via async gather/subgraph branches.

Async cancellation and cleanup policy:

- Every parallel branch runs with an explicit per-task timeout and a global stage timeout.
- On timeout, pending sibling tasks are cancelled deterministically.
- Cancellation uses structured cleanup hooks to release network clients, DB cursors, and temporary memory objects.
- Orchestration awaits cancellation completion (`gather(..., return_exceptions=True)`) to guarantee no orphaned tasks.
- Timed-out branches are marked `partial` with retryable error classification.

Aggregation policy:

- preserve each agent output independently,
- flag per-agent failures as partial, not global hard failure,
- synthesize with confidence weighting based on agent confidence and data coverage.

## 9) Confidence-Weighted Synthesis

Synthesis combines agent outputs into structured thesis:

- weighted support/opposition signals,
- evidence map by dataset,
- unresolved contradictions,
- explicit `INSUFFICIENT DATA` per unsupported claim.

Confidence computation is deterministic (Python), using:

- agent confidence,
- data completeness,
- critic penalties,
- contradiction penalties.

Confidence lifecycle (formal):

1. `synthesis_confidence`
   - computed by synthesis from weighted agent evidence and completeness.
2. `adjusted_confidence`
   - computed after critic penalties (`hallucination_penalty`, `contradiction_penalty`, `freshness_penalty`, `weak_evidence_penalty`).
3. `smoothed_confidence`
   - moving average of last `N=3` adjusted confidences.
4. `confidence_score`
   - authoritative routing value set equal to `smoothed_confidence`.
5. `final_confidence`
   - post-validation confidence in released output.

Stability rule:

- Router MUST use `confidence_score` (`smoothed_confidence`) and MUST NOT route on raw `synthesis_confidence`.

No LLM arithmetic for final score derivation.

## 10) Critic / Evaluator Behavior

Critic checks:

- hallucination risk (claim with no evidence link),
- contradictions across agents,
- weak or circular reasoning,
- overreach beyond available data.
- stale-data impact on claim validity and evidence recency.

Critic emits:

- `decision: approve|retry|conflict|insufficient_data`,
- issue taxonomy,
- remediation hints.
- deterministic penalty vector applied to `adjusted_confidence`.

Hard evidence rejection rule:

- Define `EVIDENCE_STRENGTH_THRESHOLD` (default `0.55`).
- If `evidence_strength < EVIDENCE_STRENGTH_THRESHOLD`, critic must emit `decision=retry` unless retry budget is exhausted.
- System must reject success termination even when confidence is otherwise high if evidence threshold is not met.

## 11) Reflection and Self-Improvement

Reflection consumes critic issues + run history and returns:

- root cause category (missing data, weak task decomposition, conflicting assumptions, low evidence quality),
- revised plan directives,
- retry strategy suggestion (what to rerun, what to skip).
- task reprioritization directives (promote high-signal tasks, demote low-impact expensive tasks).

Router integrates reflection updates into next actions.

## 12) Conflict Resolution

Conflict resolver activates when critic returns `conflict`.

Resolution logic:

1. classify conflict type (temporal mismatch, metric mismatch, interpretation mismatch),
2. normalize evidence windows,
3. arbitrate by evidence quality and data recency,
4. produce reconciled signal set + residual uncertainty.

If unresolved after retry budget, state terminates with explicit contested conclusion marker.

Router conflict transition invariant:

- `critic_decision == conflict` always transitions to `run_conflict_resolution`, then `run_synthesis`, then `run_critic`.
- No direct transition from `run_conflict_resolution` to `run_validation` is allowed.

## 13) Validation Gate

Final validation performs sanity checks before output release:

- schema completeness,
- prohibition checks (no fabricated numerics, no guaranteed-return language),
- evidence links for all key assertions,
- confidence and insufficiency fields present.
- final output schema contract completeness.

Validation may return `partial` if compliant but data-incomplete.

Final output contract (strict invariant):

```json
{
  "status": "success | partial | insufficient_data | failure",
  "decision": "buy | hold | sell | watchlist | no_call",
  "confidence_score": 0.0,
  "final_confidence": 0.0,
  "key_drivers": [],
  "risks": [],
  "data_used": {
    "ohlcv": {},
    "news": {},
    "fundamentals": {},
    "macro": {}
  },
  "insufficiency_markers": [],
  "reasoning": "string",
  "next_action": "string"
}
```

- Validation must fail closed if any required field is missing.

## 14) Failure Handling Strategy

Failure classes:

- `retryable_transient` (provider timeout, temporary tool failure),
- `retryable_quality` (critic weak reasoning),
- `non_retryable_contract` (invalid schema from node),
- `budget_exceeded`.

Strategy:

- exponential backoff for transient fetch failures,
- capped retries per node/domain,
- partial continuation when one research branch fails,
- termination with best available result + explicit insufficiency metadata.
- timeout-driven cancellation and guaranteed cleanup for async branches.

No silent failures; all failures appended to `errors` and `history`.

## 15) Graceful Termination Rules

Terminate when:

- success criteria met,
- or `iteration_count >= 8`,
- or any critical retry counter exceeds `3`,
- or critic determines permanent insufficiency.

Termination output includes:

- `status: success | partial | insufficient_data | failure`,
- `decision`,
- consolidated `reasoning`,
- global `confidence_score` (authoritative routing confidence at termination),
- `final_confidence` (post-validation publication confidence),
- `key_drivers`,
- `risks`,
- `data_used`,
- `next_action` recommendation,
- per-claim insufficiency disclosures (`insufficiency_markers`).

## 16) Example End-to-End Execution Trace

1. Router -> Goal/Hypothesis
2. Router -> Data Checker (news missing, fundamentals partial)
3. Router -> Data Planner
4. Router -> Data Fetch (fetch news + fundamentals delta)
5. Router -> Data Checker (now partial-but-usable)
6. Router -> Research Planner
7. Router -> Parallel Execution (fundamental/sentiment/macro)
8. Router -> Synthesis
9. Router -> Critic (decision=`conflict`)
10. Router -> Conflict Resolution
11. Router -> Synthesis (revised)
12. Router -> Critic (decision=`approve`, confidence 0.79)
13. Router -> Validation (pass)
14. Router -> terminate_success

Alternate branch:

- if fetch fails repeatedly and critical data remains missing -> `terminate_insufficient_data` with best available structured output.

## 17) Logging and Observability

Each node logs structured events:

- `request_id`, `node`, `iteration_count`, `retry_count`, latency, status.

History entries capture:

- router decision,
- input summary,
- output summary,
- confidence delta,
- errors.
- confidence lifecycle snapshots (`synthesis_confidence`, `adjusted_confidence`, `smoothed_confidence`, `final_confidence`).

This provides deterministic replay and auditability.

## 18) Dead Code Elimination Plan

During implementation, remove:

- obsolete route functions tied to linear flow,
- stale node map entries not used by new router,
- superseded prompt keys,
- tests asserting retired contracts.

Guardrail:

- run import/lint/tests to prove no unreachable references remain.

## 19) Acceptance Criteria

The replacement is accepted only if all are true:

1. All required agent types exist and are wired through router decisions.
2. Control flow is state-driven and loop-based, not linear hardcoded.
3. All node outputs include `reasoning`, `confidence_score`, `next_action`.
4. Critic, reflection, and conflict resolution loops are executable.
5. Partial data is supported and surfaced explicitly.
6. Limits (`MAX_ITERATIONS=8`, `RETRY_LIMIT=3`, `CONFIDENCE_THRESHOLD=0.75`) are enforced.
7. Final outputs never invent missing values and use `INSUFFICIENT DATA` where required.
8. Old orchestration dead code is removed.

## 20) Implementation Readiness

This document defines the complete replacement architecture and is ready for implementation planning (task decomposition, file-by-file changes, tests-first strategy).
