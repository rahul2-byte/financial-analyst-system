# AGENT ORIENTATION & COMPLIANCE PROTOCOL

## 1. System Identity & Mission
You are an agent operating within **FIN-AI**, a production-grade Financial Intelligence Platform.
- **Goal:** Deliver deterministic data processing and synthesis-driven investment research.
- **Mission:** Bridge raw data and reasoning while maintaining absolute integrity.

**CRITICAL MANDATE:** LLMs must **NEVER** perform mathematical computations, financial ratio calculations, or time-series forecasting. All quantitative logic must be implemented in Python within the `backend/` directory.

---

## 2. Repository Architecture
- **`backend/`**: FastAPI (3.11+), Quant Engine, Multi-agent Orchestration, and CLI runtime.
  - `agents/`: Single-responsibility agents (Fundamental, Technical, Risk, etc.).
  - `quant/`: Deterministic logic for financial indicators and scanners.
  - `app/`: Core services, routes (`/api/chat`, `/api/health`), and Pydantic config.
  - `.finai/`: Local run artifacts; provider results remain in current graph state.
- **`ai_engineering/`**: Governance layer containing `PROJECT_CONSTITUTION.md` and `CODING_STANDARDS.md`.

---

## 3. Operational Commands

### Environment & Dependencies
- **Backend:** `uv sync`

### Running Tests
- **Backend (Pytest):**
  - Full suite: `uv run pytest backend/tests`
  - Single File: `uv run pytest backend/tests/quant/test_sector_risk.py`
  - Single Test: `uv run pytest backend/tests/quant/test_sector_risk.py::test_calculation`

### Linting & Formatting
- **Backend (Ruff):** `uv run ruff check backend/` and `uv run ruff format backend/`
- **Backend (Types):** `uv run mypy backend/`

---

## 4. Module-Centric Reference

### A. Orchestration (The Engine)
- **Primary Class:** `PipelineOrchestrator` (`backend/app/core/orchestrator.py`)
- **Planning Flow:** `PlannerAgent` (`backend/agents/orchestration/planner.py`) generates a `PlanData` DAG (list of `ExecutionStep`).
- **Execution:** `PipelineOrchestrator` groups steps by dependencies for parallel execution and routes tasks to specialized agents.
- **Synthesis Pattern:** Multi-stage: LLM Draft -> `VerificationAgent` (Numeric Consistency) -> `ValidationAgent` (Compliance/Safety).

### B. Agent Development Protocol
- **Base Class:** `BaseAgent` (`backend/agents/base.py`). All agents MUST inherit this and implement `async def execute(self, user_query: str, step_number: int)`.
- **Response Schema:** Use `AgentResponse` (`backend/agents/data_access/schemas.py`) for standard `{status, data, errors}` output.
- **Synthesis Validation:** Use `ValidationResult` for compliance checkpoints.
- **Rules:**
  1. **Single Responsibility:** One agent = One task.
  2. **Synthesis Grounding:** Every synthesis must be grounded in verified quantitative data.
  3. **Real-time Feedback:** Use `await self.emit_status(...)` for progress updates.

### C. Data Pipeline (The Source)
- **Interfaces:** Providers expose fetch methods; graph state is the run boundary.
- **Flow:** Fetch -> Validate -> Normalize -> Pass to graph state -> Write local artifact.
- **Normalization:** SI Units, ISO Currencies (no local currency scaling in logic).
- **Integrity:** No sentiment analysis or LLM logic inside the raw data pipeline.

---

## 5. Coding Standards & Style Guidelines

### Python (Backend)
- **Version:** Python 3.11+ (Strict typing mandatory).
- **Imports:** Use **absolute imports** relative to `backend/` (e.g., `from app.core.logging import logger`).
- **Validation:** Use **Pydantic v2** for all schemas, API models, and settings.
- **Math/Quant:** Use NumPy or Pandas for vectorization. **No Python loops** for quantitative logic.
- **Style:** PEP8 compliant, no global state, no magic numbers, no circular imports.
- **Architecture:** Dependency Injection and interface-based design. Configuration via environment.
- **Logging:** Structured logging with execution time tracking and error categorization.
- **Testing:** Unit tests required for all new logic. Edge case handling is mandatory.

---

## 6. Integrity Rules (Constitution)
- **Rule #1**: LLM reasoning != Computation. Keep them strictly separate.
- **Rule #2**: All data sources must define: **Fetch, Validate, Normalize, Store**.
- **Rule #3**: No architectural drift. Check `ai_engineering/` before changing patterns.
- **Rule #4**: No secrets in source. Use `.env` and `app.config.settings`.
- **Rule #5**: All data used for investment theses must be verified and deterministic.
- **Rule #6**: Market data must be normalized to standard SI units and ISO currency codes.
- **Rule #7**: One agent = One responsibility. No modular overlapping.
- **Rule #8**: All investment reasoning must be grounded in verified quantitative data points.

---

## 7. Data Pipeline & Infrastructure
- **Pipeline Integrity:** No sentiment analysis or LLM logic allowed inside the raw data pipeline.
- **Sources:** Explicitly defined modules for News, Market Data, and Filings.
- **Flow:** Every data point must be Validated and Normalized before Storage.
- **Logs:** All pipeline steps must log execution time and source attribution for audit trails.
- **Inference:** Uses Hive's OpenAI-compatible GLM-5.3-Flash API.
- **Observability:** Uses local run metrics and artifact metadata without a telemetry SDK.

---

## 8. Development Boot Sequence
Before submitting any code changes, agents must:
1. **Load Context**: Read `PROJECT_CONSTITUTION.md`, `CODING_STANDARDS.md`, `AGENT_RULES.md`, and **Section 9 (Behavioral Guidelines)**.
2. **Verify Patterns**: Use `glob`/`grep` to find existing implementations of similar logic.
3. **Plan & Summarize**: Summarize current task and identify impacted modules before writing code.
4. **TDD**: Write unit tests for new quant logic or tools BEFORE implementation.
5. **Self-Verify**: Ensure the backend test and lint checks pass.
6. **Commit Message**: Use semantic prefixes (e.g., `feat(quant):`, `fix(agent):`).
7. **Compliance Check**: Confirm changes align with system boundaries and LLM limitations.

---

## 9. Behavioral & Philosophical Guidelines
These rules represent the core interaction principles for all agents and MUST be followed at all times.

### A. Think Before Coding
**Don't assume. Don't hide confusion. Surface tradeoffs.**
- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### B. Simplicity First
**Minimum code that solves the problem. Nothing speculative.**
- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
- Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### C. Surgical Changes
**Touch only what you must. Clean up only your own mess.**
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

### D. Goal-Driven Execution
**Define success criteria. Loop until verified.**
- Transform tasks into verifiable goals (e.g., "Add validation" -> "Write tests for invalid inputs, then make them pass").
- For multi-step tasks, state a brief plan:
  1. [Step] → verify: [check]
  2. [Step] → verify: [check]
  3. [Step] → verify: [check]
- Strong success criteria enable independent looping.

**End of Protocol.**
