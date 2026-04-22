# Long-Running Agent Harness Framework: End-to-End Evaluation

## Section A — Executive Summary

The FIN-AI backend harness utilizes a LangGraph-based state machine intended to orchestrate a complex pipeline of data-fetching, research, synthesis, and validation agents. While the framework exhibits **strong observability and tracing**, its core architecture fundamentally **fails the requirements of a production-grade long-running agent harness**. 

The current implementation is an in-memory workflow engine masquerading as a durable agent harness. It suffers from a massive "God State" object, severe architectural drift from the project's own constitution, and zero durable checkpointing. If the Python process restarts, all inflight agent task state, fetched data, and reasoning context are permanently lost. Furthermore, the decision to implement agents as raw functions that mutate a global state dictionary—rather than bounded, isolated classes—destroys single-responsibility guarantees and makes the system dangerously fragile during retry loops.

**Top Architectural Problems:**
1. **No Durable Execution:** The graph executes entirely in memory (`astream_events` in `PipelineOrchestrator`). There is no checkpointer configured. It cannot survive process restarts, making it inherently unsafe for long-running financial research tasks.
2. **The "God State" Anti-Pattern:** `ResearchGraphState` contains over 50 fields mixing system routing logic, raw dataset payloads, LLM context, and agent errors into a single dictionary.
3. **Severe Architectural Drift:** `AGENTS.md` mandates that all agents inherit from `BaseAgent` and implement `async def execute()`. In reality, the codebase uses loosely typed async functions (e.g., `router_node(state: dict[str, Any])`) that have unchecked access to the entire system state.

---

## Section B — System Understanding

**Main Flow:**
1. User queries enter via `PipelineOrchestrator.execute_query()`.
2. The orchestrator initializes a massive `ResearchGraphState` dictionary and starts the LangGraph execution loop (`astream_events`).
3. Execution enters the `router_node`, which acts as the brain, determining the next node to execute based on state flags.
4. Nodes (implemented as standalone functions like `data_fetch_node`, `research_execution_node`, `synthesis_node`) are executed sequentially or in parallel batches.
5. Nodes read the global `state` dict, perform their specific tasks, and return partial dictionary payloads.
6. LangGraph uses custom reducers (`merge_dicts`, `operator.add`, `replace_value`) to mutate the global state with the node's returned payload.
7. The loop repeats until the `router_node` yields a `terminate_*` decision.

**State Flow:** State flows as a single, globally expanding context window. Raw market data, errors, iteration counts, and router decisions are merged continuously.

**Error Flow:** Errors are caught inside nodes and appended to a global `errors` list using `operator.add`. `PipelineOrchestrator` catches catastrophic graph failures, emits trace diagnostics to Langfuse, and streams an error event to the client.

---

## Section C — Deep Evaluation by Dimension

### 1. Architecture and Design Intent
*   **What exists now:** A centralized state machine orchestrator using LangGraph.
*   **What is good:** Clear separation of nodes into specific phases (goal, data_plan, data_fetch, research_plan, synthesis, critic, evaluator).
*   **What is weak or broken:** The system boundary between "orchestration framework" and "agent business logic" does not exist. Agents receive the entire graph state and must know how to format their output to satisfy the graph's global reducer (`merge_dicts`).
*   **Why it matters:** Agents cannot be tested or executed in isolation without mocking the entire graph state.
*   **Risk Level:** **High**.
*   **Recommended fix:** Isolate agent execution context. Agents should receive only their specific inputs (`AgentExecutionInput`) and return strict `AgentResponse` objects, leaving the framework to handle state mapping.

### 2. Long-Running Agent Lifecycle
*   **What exists now:** In-memory async execution loop with hard timeouts via `asyncio.wait_for`.
*   **What is good:** `run_parallel_with_timeout` prevents infinite hanging on sub-agent tasks.
*   **What is weak or broken:** No ability to pause, sleep, or durably resume. No workflow checkpointer.
*   **Why it matters:** A deployment, pod rotation, or OOM kill mid-research destroys the entire workflow and forces a complete restart from step 1.
*   **Risk Level:** **Critical**.
*   **Recommended fix:** Integrate LangGraph's `AsyncPostgresSaver` or migrate to a truly durable execution engine like Temporal.

### 3. Harness Framework Rules and Concepts
*   **What exists now:** Event-driven stream consumption (`astream_events`), but wholly non-idempotent node logic.
*   **What is good:** Strict output contracts enforced via `finalize_node_output`.
*   **What is weak or broken:** Retries are non-idempotent. Because state reducers use `operator.add` for lists like `errors` and `executed_steps`, retrying a failed node duplicates the list contents. `merge_dicts` has no tombstone mechanism to delete stale keys.
*   **Why it matters:** A retry loop will exponentially bloat the context window and pass stale/duplicate data to the LLM.
*   **Risk Level:** **High**.
*   **Recommended fix:** Nodes must yield state *replacements* or distinct versions per iteration, rather than blindly merging and appending to global arrays.

### 4. Agent Orchestration Quality
*   **What exists now:** A hybrid routing model where `router_node` dictates stage transitions, and `research_execution_node` spawns parallel sub-agents (fundamental, technical, etc.).
*   **What is good:** Sub-agents are spawned dynamically based on the plan (`runnable_tasks`), and the framework handles dependency graphs (DAG) for parallel execution. `partial` success states are allowed if non-required agents fail.
*   **What is weak or broken:** The constitution explicitly mandates `One agent = One responsibility. No modular overlapping.` However, since every agent receives the full `state` dictionary, any agent can silently depend on or modify fields meant for another agent. 
*   **Why it matters:** It breeds hidden coupling and makes debugging agent hallucinations nearly impossible.
*   **Risk Level:** **Medium**.
*   **Recommended fix:** Enforce strict payload isolation in `research_execution_node`—pass only the evaluated `AgentExecutionInput` to the sub-agent, not the whole `state` dictionary.

### 5. State, Memory, and Context Management
*   **What exists now:** `ResearchGraphState` with 50+ fields, combined with external database persistence for raw financial data (`storage/` layer).
*   **What is good:** Raw data (OHLCV, News) is intelligently pushed to structured storage (Timescale/pgvector) immediately upon fetch via `persistence.py`, preventing the graph state from holding gigabytes of raw time-series data.
*   **What is weak or broken:** Short-term and long-term context are completely intermixed. LLM context compaction is non-existent at the framework level. The `agent_outputs` dictionary grows monotonically.
*   **Why it matters:** Prompt drift over long runs. The LLM gets confused by previous iteration errors that were never cleaned up.
*   **Risk Level:** **High**.
*   **Recommended fix:** Implement a "State Compactor" node that runs at the end of every major phase to summarize findings and prune dead/stale context before the next routing decision.

### 6. Failure Handling and Fault Tolerance
*   **What exists now:** Circuit breakers, retry counters (`retry_count_by_domain`), and global exception catching in the orchestrator.
*   **What is good:** The system degrades gracefully to `status: "low_confidence"` or `partial` success rather than crashing the API response entirely.
*   **What is weak or broken:** If the `merge_dicts` reducer fails due to a type mismatch injected by an LLM hallucination, the state becomes irrecoverably corrupted. 
*   **Why it matters:** The system treats LLM output as safe for global state mutation without intermediate type validation on deeply nested fields.
*   **Risk Level:** **High**.
*   **Recommended fix:** Validate all node outputs strictly against Pydantic models before allowing LangGraph to merge them into the global state.

### 7. Observability and Debuggability
*   **What exists now:** Extensive, high-quality tracing using `langfuse_context` and a custom `SessionLogger`.
*   **What is good:** Exceptional step-level execution visibility. Audit contexts `_build_audit_context` capture snapshots of state transitions, loop warnings, and error counts.
*   **What is weak or broken:** Debugging is still painful because you must visually diff a massive JSON blob (`state_summary`) between trace spans to figure out what a node actually mutated.
*   **Why it matters:** Developer ergonomics suffer when the payload of a trace is an indistinguishable 500-line JSON object.
*   **Risk Level:** **Low**.
*   **Recommended fix:** Log *deltas* (jsonpatch) of state transitions rather than full state snapshots.

---

## Section D — Code Smells and Anti-Patterns

*   **Architectural Drift / The "Documentation Lie":** `AGENTS.md` explicitly commands developers to use `BaseAgent` and OOP interfaces. The actual framework completely ignores this, using raw functions like `router_node(state)`.
*   **God State (`ResearchGraphState`):** Violates Interface Segregation. The `evaluator_node` does not need access to `fetched_data`, but it gets it anyway.
*   **Implicit State Transitions:** The `merge_dicts` recursive reducer silently updates deeply nested dictionaries, making it impossible to statically analyze which node modifies which data.
*   **Non-Idempotent Appends:** `errors: Annotated[List[str], operator.add]` causes linear growth of the same errors during retry loops.

---

## Section E — Missing Harness Capabilities

1.  **Durable Checkpointing:** The absolute most critical missing piece. LangGraph requires a `checkpointer` to save state to a database. Without it, this is just a fancy Python script.
2.  **Workflow Suspension / Sleep:** No ability for an agent to say "Wait 5 minutes for the API rate limit to reset" without blocking the event loop.
3.  **Human-in-the-Loop Interruption:** The graph can output `awaiting_user_input`, but because state isn't durably persisted, the user's response will hit a new API request that has no memory of the suspended graph.
4.  **Strict Context Sandbox:** Agents operate globally rather than in a localized context sandbox.

---

## Section F — Refactor / Redesign Plan

**Target Architecture:**
1.  **Persistence Layer Integration:** Inject `AsyncPostgresSaver` into the `StateGraph` compilation in `graph_builder.py`. Use the `run_id` as the thread ID to enable true resumability.
2.  **State Machine Redesign:** Break `ResearchGraphState` into three distinct, non-overlapping channels:
    *   `ControlState`: Iteration counts, routing decisions, errors.
    *   `ContextState`: The actual prompt context, continuously summarized/compacted.
    *   `DataManifest`: Pointers to the database where raw data lives (no actual data in graph state).
3.  **Agent Sandbox Model:** Conform to the constitution. Resurrect `BaseAgent`. The graph node should instantiate the `BaseAgent`, map the `GraphState` to a strict `AgentExecutionInput` Pydantic model, execute the agent, and map the `AgentResponse` back into state mutations.
4.  **Idempotent Retries:** Change array appends (`operator.add`) to dictionary overwrites keyed by `run_id` or `iteration_count` to prevent array bloat on retries.

---

## Section G — Priority Fix Roadmap

*   **Immediate Critical Fixes:** 
    *   Implement LangGraph Checkpointing (`AsyncPostgresSaver`) to prevent total data loss on server restarts.
    *   Update `AGENTS.md` to reflect the functional node reality OR rewrite the nodes to use the documented `BaseAgent` interface.
*   **Short-Term Structural Improvements:**
    *   Fix the `operator.add` reducers on `errors` and `executed_steps` to be idempotent based on step IDs.
    *   Introduce Pydantic validation *before* `merge_dicts` executes to prevent global state corruption.
*   **Medium-Term Architectural Upgrades:**
    *   Implement an explicit `Context Compaction` node that runs before the `router` to summarize LLM memory and prevent context window exhaustion.
    *   Enforce the "Agent Sandbox" model where sub-agents only receive specific sub-trees of the state.
*   **Long-Term Platform Improvements:**
    *   Migrate orchestration from LangGraph to a true durable execution framework (like Temporal) if human-in-the-loop wait times exceed minutes or hours, as holding Python async loops open indefinitely is an anti-pattern.
