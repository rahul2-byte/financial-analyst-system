# ARCHITECTURE DECISIONS & SESSION MEMORY

## Context: The "Deep Financial Analyst" Architecture

### 1. The Initial Vision vs. The Reality Check
We explored building a "Deep Financial Analyst" using a multi-agent system. Initially, the idea was to have multiple autonomous agents communicating with each other, making decisions on what tools to use, what sub-agents to call, and determining the next steps dynamically (similar to frameworks like AutoGen or CrewAI).

**The Brutal Truth:** We concluded that for a production-grade financial system, allowing agents to converse and autonomously decide execution paths is a **terrible idea**. 
- **Risks:** It leads to hallucinations, infinite loops, drift from the original prompt, and non-deterministic behavior. 
- **Costs:** It is incredibly slow and expensive due to massive context windows being passed back and forth between agents.
- **Compliance:** It violates the core rule that LLMs must NEVER perform mathematical computations or dictate unchecked logic.

### 2. The Final Decision: Deterministic, Tool-Driven Approach
We decided to stick strictly to the original constraints defined in `ORCHESTRATION_RULES.md` and `AGENT_RULES.md`.

**The chosen paradigm:**
- **No Agent-to-Agent Chatter:** Agents do not talk to each other.
- **Single Router/Planner:** A single, powerful LLM acts as the brain/router. It generates a strict JSON plan.
- **Dumb, Reliable Tools:** The system relies on highly reliable Python functions (tools) for web searching, DB querying, and quantitative math. The LLM only picks the tool and reads the output; Python does the actual work.
- **Deterministic Orchestration:** Execution order is strictly controlled by a deterministic state machine or DAG.

### 3. The Chosen MLOps Stack
To support this high-speed, memory-optimized, open-source architecture, we selected the following stack:

1.  **Agent Execution & Validation: `Instructor` + `LiteLLM`**
    *   **Why:** `Instructor` wraps LLM clients and forces them to return data that perfectly validates against Pydantic schemas (zero-overhead compliance with the "Structured JSON" rule). `LiteLLM` standardizes API calls across 100+ models, handles rate limiting, and supports local models like `llama.cpp`.

2.  **Orchestration: `LangGraph` deterministic state graph**
    *   **Why:** The runtime uses explicit graph nodes and dependency-aware execution with deterministic routing and retries. This keeps execution auditable and prevents autonomous agent drift.

3.  **Observability & Tracing: OpenTelemetry + Phoenix**
    *   **Why:** The backend emits structured tracing spans via OTLP to Phoenix, enabling request-level execution auditability for node transitions, LLM calls, and tool execution events.

4.  **Vector Storage: `Qdrant`**
    *   **Why:** Already in the stack. Blazing fast (Rust-based) and memory-efficient, perfect for storing and retrieving chunked financial reports with complex payload filtering.

### Benefits of this Approach
- **Auditability:** Every step, tool call, and mathematical calculation can be traced and audited.
- **Speed & Cost:** Only one LLM reasons at a time, drastically reducing token usage and latency.
- **Reliability:** Python handles the math and logic, eliminating the risk of LLM calculation errors.
- **Strict Compliance:** Perfectly aligns with the project's constitution and agent rules.
