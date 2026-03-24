# AGENT ORIENTATION & COMPLIANCE PROTOCOL

## 1. System Identity & Mission
You are an agent operating within **FIN-AI**, a production-grade Financial Intelligence Platform.
- **Goal:** Deliver deterministic data processing and synthesis-driven investment research.
- **Mission:** Bridge raw data and reasoning while maintaining absolute integrity.

**CRITICAL MANDATE:** LLMs must **NEVER** perform mathematical computations, financial ratio calculations, or time-series forecasting. All quantitative logic must be implemented in Python within the `backend/` directory.

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
  - Debugging: `pytest -s backend/tests`
- **Frontend (Vitest):**
  - Run once: `npm run test` (from `frontend/`)
  - Single File: `npx vitest frontend/tests/unit/Chart.test.tsx`
  - Watch Mode: `npm run test:watch`
  - Coverage: `npm run test:coverage`
- **E2E (Playwright):** `npm run test:e2e`

### Linting & Formatting
- **Backend (Ruff):** `ruff check backend/` and `ruff format backend/`
- **Backend (Types):** `mypy backend/`
- **Frontend (ESLint):** `npm run lint`

---

## 4. Coding Standards & Style Guidelines

### Python (Backend)
- **Version:** Python 3.11+ (Strict typing mandatory).
- **Imports:** Use **absolute imports** relative to `backend/` (e.g., `from app.core.logging import logger`).
- **Validation:** Use **Pydantic v2** for all schemas, API models, and settings.
- **Math/Quant:** Use NumPy or Pandas for vectorization. **No Python loops** for quantitative logic.
- **Error Handling:** Use `logger.error(..., exc_info=True)` for traceability. No silent failures.
- **Statelessness:** No global state. Use FastAPI dependency injection for services.
- **Naming:** `snake_case` (files/vars), `PascalCase` (classes).

### TypeScript/React (Frontend)
- **Frameworks:** Next.js 16+, React 19 (Server Components preferred).
- **Styling:** Tailwind CSS 4. Use `clsx` and `tailwind-merge` for class utility management.
- **Components:** Modular, functional components with explicit TypeScript prop interfaces.
- **State Management:** Prioritize React Hooks (`useState`, `useMemo`, `useCallback`) and local state.
- **Naming:** `PascalCase` (Components), `camelCase` (Variables/Methods).

---

## 5. Agent Development Protocol
When modifying or creating Agents in `backend/agents/`:
1. **Single Responsibility:** One agent = One task. No "god agents".
2. **Deterministic Flow:** Agent -> Quantitative Tool (Python) -> Synthesis (LLM).
3. **Synthesis Grounding:** Every synthesis must be grounded in verified quantitative data.
4. **Structured Output:** Always return JSON validated by a Pydantic schema:
   ```json
   {"status": "success", "data": {...}, "errors": null}
   ```
5. **Real-time Feedback:** Use `await self.emit_status(...)` for progress updates.
6. **Orchestration:** Agents must not self-trigger; all actions go through the Orchestrator.

---

## 6. Integrity Rules (Constitution)
- **Rule #1**: LLM reasoning != Computation. Keep them strictly separate.
- **Rule #2**: All data sources must define: **Fetch, Validate, Normalize, Store**.
- **Rule #3**: No architectural drift. Check `ai_engineering/` before changing patterns.
- **Rule #4**: No secrets in source. Use `.env` and `app.config.settings`.
- **Rule #5**: All data used for investment theses must be verified and deterministic.
- **Rule #6**: Market data must be normalized to standard SI units and ISO currency codes.

---

## 7. Data Pipeline & Infrastructure
- **Pipeline:** No sentiment analysis or LLM logic inside the raw data pipeline.
- **Logs:** All pipeline steps must log execution time and source attribution.
- **Configuration:** Managed via Pydantic settings in `backend/app/config.py`.
- **Inference:** Uses `llama.cpp` for local inference and OpenTelemetry for observability.

## 8. Development Boot Sequence
Before submitting any code changes, agents must:
1. **Read Constitution**: Verify alignment with `ai_engineering/PROJECT_CONSTITUTION.md`.
2. **Verify Patterns**: Use `glob`/`grep` to find existing implementations of similar logic.
3. **TDD**: Write unit tests for new quant logic or tools BEFORE implementation.
4. **Self-Verify**: Ensure `pytest`, `ruff check`, and frontend `npm run lint` pass.
5. **Commit Message**: Use semantic prefixes (e.g., `feat(quant):`, `fix(agent):`).

**End of Protocol.**
