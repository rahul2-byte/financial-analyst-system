# AGENT ORIENTATION & COMPLIANCE PROTOCOL

## 1. System Identity & Mission

You are operating within a **Production-Grade Financial Intelligence Platform**.
Your primary directive is to build a modular, multi-agent system where:
- **Deterministic Logic** handles data processing and calculation.
- **LLMs** handle reasoning, strategy, and synthesis.

**CRITICAL MANDATE:**
LLMs must **NEVER** perform mathematical computations, financial ratio calculations, or time-series forecasting. All quantitative logic must be implemented in Python within the `backend/` directory.

---

## 2. Repository Architecture

The repository is structured to separate Logic, Interface, and Governance.

- **`backend/`**: The Backend Server Root.
  - Contains all Python source code: Quant Engine, Agents, Orchestrator, API.
  - This is the execution root for the backend server.
- **`frontend/`**: The Frontend Application Root.
  - Contains React/Next.js application code.
  - This is the execution root for the frontend application.
- **`ai_engineering/`**: The "Main Memory" & Governance Layer.
  - Contains all architectural rules, constitutions, and policies.
  - **READ-ONLY**: You must consult these files but never modify them without explicit authorization.
  - Key files: `PROJECT_CONSTITUTION.md`, `CODING_STANDARDS.md`, `AGENT_RULES.md`.

---

## 3. Operational Commands

Execute these commands from their respective root directories.

### Environment & Dependencies
- **Install Backend Dependencies:**
  ```bash
  pip install -r backend/requirements.txt
  ```
- **Install Frontend Dependencies:**
  ```bash
  cd frontend && npm install
  ```

### Testing (Pytest)
- **Run All Tests:**
  ```bash
  pytest backend/tests
  ```
- **Run Specific Test File:**
  ```bash
  pytest backend/tests/quant/test_sector_risk.py
  ```
- **Run with Output Logs (Debug):**
  ```bash
  pytest -s backend/tests
  ```
- **Run with Coverage:**
  ```bash
  pytest --cov=backend backend/tests
  ```

### Code Quality & Linting
- **Lint (Ruff):**
  ```bash
  ruff check backend/
  ```
- **Format (Ruff):**
  ```bash
  ruff format backend/
  ```
- **Type Check (Mpy):**
  ```bash
  mypy backend/
  ```

---

## 4. Coding Standards & Style Guidelines

Adherence to `ai_engineering/CODING_STANDARDS.md` is mandatory.

### Python Development (Backend)
- Version: Python 3.11+
- Style: PEP8 compliant (enforced by Ruff).
- Imports:
  - Use **absolute imports** relative to the `backend/` directory root.
  - *Correct:* `from common.schemas import SectorMetrics`
  - *Incorrect:* `from backend.common.schemas import SectorMetrics`
  - *Incorrect:* `from ..common.schemas import SectorMetrics`
  - **No circular imports.** Use dependency injection or restructuring to resolve cycles.

### Typing & Schemas
- **Strict Typing:** All function signatures must have type hints.
  ```python
  def calculate_risk(self, data: List[float]) -> float:
  ```
- **Data Validation:** Use **Pydantic v2** or `dataclasses` for all data structures.
  - Raw dictionaries are forbidden for internal data passing.
- **No Magic Numbers:** All constants must be named and preferably loaded from configuration.

### Error Handling
- **Custom Exceptions:** Define domain-specific exceptions in `backend/common/exceptions.py`.
- **No Silent Failures:** Never use bare `try...except`. Log the error and re-raise or handle gracefully.
- **Logging:** Use structured logging (JSON format preferred). Include execution time and context.

### Performance
- **Vectorization:** Use NumPy/Pandas for data processing. Avoid Python loops for heavy computation.
- **Statelessness:** Functions should be pure where possible. Global state is forbidden.

---

## 5. Agent Development Rules

When building or modifying Agents (in `backend/agents/`):

1.  **Single Responsibility:** One agent = One task.
2.  **Stateless:** Agents must not maintain internal state between executions.
3.  **Structured Output:**
    - Agents **MUST** return structured JSON.
    - Format:
      ```json
      {
        "status": "success | failure",
        "data": { ... },
        "errors": null
      }
      ```
4.  **No Direct Communication:** Agents do not call other agents directly. All coordination is handled by the `Orchestrator`.
5.  **Prompt Engineering:** Use strict templates. Validate all LLM outputs against Pydantic schemas.

---

## 6. Development Workflow (The "Boot Sequence")

Before writing code, every active agent must:

1.  **Read Context:**
    - `ai_engineering/BOOT_SEQUENCE.md`
    - `ai_engineering/PROJECT_CONSTITUTION.md`
    - `ai_engineering/ACTIVE_TASK.md`
2.  **Explore Codebase:**
    - Use `grep` and `find` to understand existing patterns.
    - Do not assume file locations; verify them.
3.  **Plan:**
    - Formulate a plan that respects the "No LLM Math" rule.
    - Identify impacted modules.
4.  **Implement (Test-Driven):**
    - Write unit tests *first* or in parallel.
    - Implement deterministic logic in `backend/quant/` or `backend/common/`.
    - Implement agent logic in `backend/agents/`.
5.  **Verify:**
    - Run `pytest`.
    - Run `ruff check`.
    - Ensure no regression.

---

## 7. Version Control & Changelog

- **Commit Messages:** Semantic and descriptive (e.g., `feat(quant): add sector risk scoring`).
- **Changelog:** Update `CHANGELOG.md` for every architectural change or significant feature, following `ai_engineering/CHANGELOG_POLICY.md`.
- **Review:** Self-review code against `ai_engineering/CODING_STANDARDS.md` before finalizing.

**End of Protocol.**
