# Phase 1: Foundation & Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a stateful, parallel, and verifiable orchestration layer to eliminate numeric hallucinations and improve performance.

**Architecture:** 
- Centralized `ResearchState` to store every raw number fetched by tools.
- Dependency-aware `PipelineOrchestrator` using `asyncio` for parallel agent execution.
- `VerificationAgent` for post-synthesis numeric validation with a 3-strike correction loop.

**Tech Stack:** Python 3.11+, Pydantic v2, asyncio, Langfuse.

---

### Task 1: Implement ResearchState Global Registry

**Files:**
- Create: `backend/common/state.py`
- Modify: `backend/common/schemas.py`

- [ ] **Step 1: Define ToolResult and ResearchState schemas**
Create Pydantic models to track every data point fetched.

```python
# backend/common/state.py
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime

class ToolResult(BaseModel):
    tool_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    input_parameters: Dict[str, Any]
    output_data: Any # The raw JSON/Dict from the tool
    extracted_metrics: Dict[str, float] = Field(default_factory=dict) # For fast lookup

class ResearchState(BaseModel):
    query: str
    start_time: datetime = Field(default_factory=datetime.utcnow)
    tool_registry: List[ToolResult] = []
    agent_outputs: Dict[str, Any] = {}
    verification_errors: List[str] = []
    retry_count: int = 0
```

- [ ] **Step 2: Add metrics extraction helper**
Add a method to `ToolResult` that flattens nested JSON into a simple `key: value` map for the `VerificationAgent`.

- [ ] **Step 3: Commit**
```bash
git add backend/common/state.py
git commit -m "feat(orchestrator): add ResearchState for data persistence"
```

---

### Task 2: Refactor Planner for Parallelism

**Files:**
- Modify: `backend/agents/orchestration/planner.py`
- Modify: `backend/agents/orchestration/schemas.py`

- [ ] **Step 1: Update Planner System Prompt**
Instruct the Planner to actively look for independent tasks and group them using the `dependencies` list.

- [ ] **Step 2: Verify dependency logic**
Ensure the Planner doesn't create circular dependencies.

- [ ] **Step 3: Commit**
```bash
git add backend/agents/orchestration/planner.py
git commit -m "feat(planner): optimize dependency tagging for parallel execution"
```

---

### Task 3: Refactor Orchestrator for Parallelism & State

**Files:**
- Modify: `backend/app/core/orchestrator.py`

- [ ] **Step 1: Implement Task Grouping**
Create a scheduler that groups `ExecutionStep`s based on their `dependencies`.

- [ ] **Step 2: Implement Parallel Execution**
Use `asyncio.gather` to execute all steps in a group concurrently.

- [ ] **Step 3: Integrate ResearchState**
Ensure every tool call made by an agent is registered in `state.tool_registry`.

- [ ] **Step 4: Commit**
```bash
git add backend/app/core/orchestrator.py
git commit -m "feat(orchestrator): implement parallel execution and state tracking"
```

---

### Task 4: Numeric Verification Agent & Retry Loop

**Files:**
- Create: `backend/agents/quality_control/verification.py`
- Modify: `backend/app/core/orchestrator.py`

- [ ] **Step 1: Implement VerificationAgent**
The agent should use regex to find numbers in the final report and check them against `ResearchState.tool_registry`.

- [ ] **Step 2: Implement Correction Prompting**
If a mismatch is found, generate a "Correction Instruction" for the Synthesis step.

- [ ] **Step 3: Implement Orchestrator Retry Logic**
Wrap the Synthesis + Validation step in a loop that allows up to 3 retries.

- [ ] **Step 4: Commit**
```bash
git add backend/agents/quality_control/verification.py backend/app/core/orchestrator.py
git commit -m "feat(safety): add numeric verification agent and correction loop"
```

---

### Task 5: Testing & Observability

- [ ] **Step 1: Write integration test**
Create `backend/tests/integration/test_parallel_orchestrator.py`.

- [ ] **Step 2: Add Langfuse traces for parallel tasks**
Ensure parallel tasks are nested correctly in the trace UI.

- [ ] **Step 3: Commit**
```bash
git add backend/tests/integration/test_parallel_orchestrator.py
git commit -m "test(orchestrator): add integration tests for parallel flow"
```
