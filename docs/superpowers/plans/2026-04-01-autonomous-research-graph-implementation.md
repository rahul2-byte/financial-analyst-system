# Autonomous Research Graph Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current primary orchestration with a deterministic, autonomous, router-driven multi-agent research graph with critic/reflection/conflict loops, strict JSON contracts, bounded retries/iterations, and strict final output validation.

**Architecture:** Replace graph state + graph builder + research subgraph with a central router state machine. Add dedicated nodes for goal/hypothesis, data lifecycle, research planning, parallel execution, synthesis, critic, reflection, conflict resolution, and validation. Enforce confidence lifecycle and authoritative routing confidence with smoothing.

**Tech Stack:** Python 3.11+, LangGraph, Pydantic v2, pytest, ruff.

---

## Spec-to-Task Traceability (Must Pass)

- Non-negotiable invariants and acceptance criteria from the approved spec must be mapped to tests before implementation is marked complete.
- Mandatory test assertions:
  - full state schema coverage and merge semantics,
  - authoritative confidence lifecycle and router confidence source-of-truth,
  - strict JSON envelope for every node,
  - freshness penalties and refetch trigger,
  - evidence threshold hard rejection,
  - explicit conflict loop (`critic -> conflict_resolution -> synthesis -> critic`),
  - strict final output contract,
  - retry/failure taxonomy and bounded execution,
  - cost-aware routing and cache reuse,
  - dead code and stale prompt key removal.

### Task 1: Autonomous schemas + state

**Files:**
- Create: `backend/app/core/graph/autonomous_schemas.py`
- Modify: `backend/app/core/graph/graph_state.py`
- Test: `backend/tests/unit/test_autonomous_graph_state.py`

- [ ] Step 1: Write failing schema/state tests
- [ ] Step 2: Run failing tests
- [ ] Step 3: Implement schemas and state merge semantics
- [ ] Step 4: Run tests green
- [ ] Step 5: Ensure schema includes all required fields from spec section 4, including `freshness_policy`, `execution_budget`, `timeouts`, `evidence_strength`, `confidence_components`, `termination_reason`, and `final_output`

### Task 2: Deterministic router

**Files:**
- Create: `backend/app/core/graph/router_policy.py`
- Create: `backend/app/core/graph/nodes/router_node.py`
- Test: `backend/tests/unit/test_autonomous_router.py`

- [ ] Step 1: Write failing router policy tests
- [ ] Step 2: Run failing tests
- [ ] Step 3: Implement deterministic decisions
- [ ] Step 4: Run tests green
- [ ] Step 5: Add transition-table tests for conflict invariants, freshness gating, evidence gate, budget termination, and authoritative confidence-only routing

### Task 3: Data loop nodes

**Files:**
- Create: `backend/app/core/graph/nodes/goal_hypothesis_node.py`
- Create: `backend/app/core/graph/nodes/data_checker_node.py`
- Create: `backend/app/core/graph/nodes/data_planner_node.py`
- Create: `backend/app/core/graph/nodes/data_fetch_node.py`
- Test: `backend/tests/unit/test_autonomous_loops.py`

- [ ] Step 1: Write failing data loop tests
- [ ] Step 2: Run failing tests
- [ ] Step 3: Implement nodes with strict JSON envelopes
- [ ] Step 4: Run tests green

### Task 3.1: Cross-cutting node output contract

**Files:**
- Test: `backend/tests/unit/test_autonomous_node_contracts.py`

- [ ] Step 1: Write failing tests that assert all autonomous nodes return the common JSON envelope (`status`, `reasoning`, `confidence_score`, `next_action`, `data`, `errors`)
- [ ] Step 2: Run failing tests
- [ ] Step 3: Fix node outputs to satisfy contract uniformly
- [ ] Step 4: Run tests green

### Task 4: Research scheduler + async control

**Files:**
- Modify: `backend/app/core/graph/research_graph.py`
- Create: `backend/app/core/graph/async_control.py`
- Create: `backend/app/core/graph/nodes/research_planner_node.py`
- Create: `backend/app/core/graph/nodes/exec_fundamental_node.py`
- Create: `backend/app/core/graph/nodes/exec_sentiment_node.py`
- Create: `backend/app/core/graph/nodes/exec_macro_node.py`
- Test: `backend/tests/unit/test_autonomous_loops.py`

- [ ] Step 1: Write failing tests for priority and timeout/cancel behavior
- [ ] Step 2: Run failing tests
- [ ] Step 3: Implement scheduler + parallel execution + cleanup
- [ ] Step 4: Run tests green

### Task 5: Synthesis / critic / reflection / conflict loop

**Files:**
- Modify: `backend/app/core/graph/nodes/synthesis_node.py`
- Create: `backend/app/core/graph/nodes/critic_node.py`
- Create: `backend/app/core/graph/nodes/reflection_node.py`
- Create: `backend/app/core/graph/nodes/conflict_resolution_node.py`
- Test: `backend/tests/unit/test_autonomous_critic_reflection.py`
- Test: `backend/tests/unit/test_autonomous_conflict_resolution.py`

- [ ] Step 1: Write failing loop and confidence lifecycle tests
- [ ] Step 2: Run failing tests
- [ ] Step 3: Implement nodes and deterministic confidence calculations
- [ ] Step 4: Run tests green
- [ ] Step 5: Add explicit tests for hard evidence rejection (`evidence_strength < threshold` forces retry unless budget exhausted)

### Task 6: Validation + final output contract

**Files:**
- Modify: `backend/app/core/graph/nodes/validation_node.py`
- Create: `backend/app/core/graph/final_output_contract.py`
- Test: `backend/tests/unit/test_autonomous_validation.py`

- [ ] Step 1: Write failing output contract tests
- [ ] Step 2: Run failing tests
- [ ] Step 3: Implement fail-closed validation
- [ ] Step 4: Run tests green

### Task 7: Replace graph builder and remove dead code

**Files:**
- Modify: `backend/app/core/graph/graph_builder.py`
- Modify: `backend/app/core/graph/agent_map.py`
- Modify: `backend/app/core/graph/nodes/__init__.py`
- Test: `backend/tests/unit/test_graph_builder_contracts.py`

- [ ] Step 1: Write/update failing topology tests
- [ ] Step 2: Run failing tests
- [ ] Step 3: Replace builder topology and delete retired routing
- [ ] Step 4: Run tests green
- [ ] Step 5: Remove stale prompt keys/tests/import references tied only to retired flow

### Task 8: Prompt/config integration and full verification

**Files:**
- Create: `backend/config/prompts/autonomous_orchestrator.yaml`
- Test: `backend/tests/core/test_prompts.py`

- [ ] Step 1: Add failing prompt lookup tests
- [ ] Step 2: Run failing tests
- [ ] Step 3: Add prompts
- [ ] Step 4: Run full checks (`ruff`, `mypy`, `pytest`)
- [ ] Step 5: Add observability assertions for structured logs/history confidence snapshots in autonomous execution tests
