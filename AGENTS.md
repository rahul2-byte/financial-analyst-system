# AGENT ORIENTATION & COMPLIANCE PROTOCOL

## 1. System Identity & Mission
You are an agent operating within **FIN-AI**, a production-grade Financial Intelligence Platform.
- **Goal:** Deliver deterministic data processing and synthesis-driven investment research.
- **Mission:** Bridge raw data and reasoning while maintaining absolute integrity.

**CRITICAL MANDATE:** LLMs must **NEVER** perform mathematical computations, financial ratio calculations, or time-series forecasting. All quantitative logic must be implemented in Python within the `backend/` directory.

---

## 2. Repository Architecture
- **`backend/`**: FastAPI (3.11+), Quant Engine, Multi-agent Orchestration.
  - `agents/`: Single-responsibility agents (Fundamental, Technical, Risk, etc.).
  - `quant/`: Deterministic logic for financial indicators and scanners.
  - `app/`: Core services, routes (`/api/chat`, `/api/health`), and Pydantic config.
  - `storage/`: PostgreSQL (TimescaleDB for market data) and Qdrant (vector storage).
- **`frontend/`**: Next.js 16 (App Router), React 19, Tailwind CSS 4.
  - `components/`: UI blocks (Charts via Recharts, Virtual lists via TanStack).
  - `app/`: Server-side components and routing.
- **`ai_engineering/`**: Governance layer containing `PROJECT_CONSTITUTION.md` and `CODING_STANDARDS.md`.

---

## 3. Operational Commands

### Environment & Dependencies
- **Backend:** `pip install -r backend/requirements.txt`
- **Frontend:** `cd frontend && npm install`

### Running Tests
- **Backend (Pytest):**
  - Full suite: `pytest backend/tests`
  - Single File: `pytest backend/tests/quant/test_sector_risk.py`
  - Single Test: `pytest backend/tests/quant/test_sector_risk.py::test_calculation`
- **Frontend (Vitest):**
  - Run once: `npm run test` (from `frontend/`)
- **E2E (Playwright):** `npm run test:e2e` (from `frontend/`)

### Linting & Formatting
- **Backend (Ruff):** `ruff check backend/` and `ruff format backend/`
- **Backend (Types):** `mypy backend/`
- **Frontend (ESLint):** `npm run lint` (from `frontend/`)

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
- **Interfaces:** (`backend/data/interfaces/`)
  - `IDataFetcher`: `fetch_ohlcv`, `fetch_news`.
  - `IStructuredStorage`: `save_ohlcv`, `get_ohlcv`, `get_latest_date`.
  - `IVectorStorage`: `upsert_chunks`, `search` (Hybrid/Temporal).
- **Flow:** Fetch -> Validate -> Normalize -> Store.
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

### TypeScript/React (Frontend)
- **Frameworks:** Next.js 16+, React 19 (Server Components preferred).
- **Styling:** Tailwind CSS 4. Use `clsx` and `tailwind-merge` for class utility management.
- **Components:** Modular, functional components with explicit TypeScript prop interfaces.
- **State Management:** Prioritize React Hooks (`useState`, `useMemo`, `useCallback`) and local state.
- **Typing:** Strict TypeScript typing for all props, states, and API responses.

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
- **Inference:** Uses `llama.cpp` for local inference and OpenTelemetry for observability.
- **Storage:** PostgreSQL (TimescaleDB) for time-series and Qdrant for vector embeddings.

---

## 8. Development Boot Sequence
Before submitting any code changes, agents must:
1. **Load Context**: Read `PROJECT_CONSTITUTION.md`, `CODING_STANDARDS.md`, and `AGENT_RULES.md`.
2. **Verify Patterns**: Use `glob`/`grep` to find existing implementations of similar logic.
3. **Plan & Summarize**: Summarize current task and identify impacted modules before writing code.
4. **TDD**: Write unit tests for new quant logic or tools BEFORE implementation.
5. **Self-Verify**: Ensure `pytest`, `ruff check`, and frontend `npm run lint` pass.
6. **Commit Message**: Use semantic prefixes (e.g., `feat(quant):`, `fix(agent):`).
7. **Compliance Check**: Confirm changes align with system boundaries and LLM limitations.

**End of Protocol.**
