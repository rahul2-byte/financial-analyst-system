# Financial Data Nodes Refactor Design

> **Status:** Approved (behavior-preserving only)

## Goal

Refactor `backend/agents/financial/data/` to be maintainable, testable, and scalable **without changing runtime behavior or output contracts** of:

- `data_check_node(state)`
- `data_plan_node(state)`
- `data_fetch_node(state)`

“Behavior-preserving” here means:

- Node payload keys and shapes remain unchanged.
- Existing unit tests pass without modification (except for tests added to lock existing behavior).
- Dataset semantics (coverage/freshness rules, thresholds, caching, persistence side effects) remain the same.

## Current State (Facts)

Directory contents (as of 2026-04-19):

- `backend/agents/financial/data/data_fetch_node.py` (~1222 LOC)
- `backend/agents/financial/data/data_check_node.py` (~598 LOC)
- `backend/agents/financial/data/data_plan_node.py` (~79 LOC)

Observed issues from code review:

- Large god-functions mixing orchestration, IO, policy, and persistence.
- Async nodes call sync DB/vector/network methods (event-loop blocking risk).
- Global dependencies (`resources`, `settings`) are used directly (tight coupling, low testability).
- Stringly-typed state (`dict[str, Any]`) and shape-shifting payloads.
- Duplicate policy and symbol resolution logic across nodes.
- Dead/unused helpers exist in `data_fetch_node.py`.

Constraints from repository:

- Graph runtime expects node functions with current names; tests reference them.
- Node outputs are validated by `finalize_node_output()` contract requiring `status`, `reasoning`, `confidence_score`, `next_action`, `data`, `errors`.
- `ResearchGraphState` already exists as a `TypedDict` in `backend/app/core/graph/graph_state.py`.

## Non-Goals

- Switching DB clients to async.
- Changing freshness thresholds, coverage formulas, or dataset requirements.
- Adding new datasets/providers.
- Changing persistence strategy (transactions/idempotency) in this phase.

## Design Principles

1. **Stable Facade:** Keep current node entrypoints and payload shapes.
2. **Split by Responsibility:** Isolate policy, typing, symbol resolution, dataset handlers, and persistence.
3. **Pure Core, Impure Edges:** Concentrate side effects (DB/vector writes, network fetch) in explicit modules.
4. **Docstring-First Clarity:** Every new module/function should be understandable without reading its internals.
5. **Mechanical Equivalence:** Each refactor step maps 1:1 to existing logic (with line references in docstrings).

## Target Architecture

### Public API (unchanged)

Keep these files and their exported async functions:

- `backend/agents/financial/data/data_fetch_node.py`: `data_fetch_node(state)`
- `backend/agents/financial/data/data_check_node.py`: `data_check_node(state)`
- `backend/agents/financial/data/data_plan_node.py`: `data_plan_node(state)`

Each becomes a thin orchestrator delegating to internal modules.

### Internal Modules (new)

Create new internal modules under `backend/agents/financial/data/`.

#### 1) `_types.py`

Purpose: typed internal contracts for this refactor.

Contents:

- `DataPlanItem` (`TypedDict`) matching current plan item shape:
  - `dataset: str`
  - `priority: str` (e.g., `P0`, `P1`)
  - `action: str` (e.g., `fetch`, `refresh`, `materialize`)
  - `requirements: dict[str, Any]`
- `DatasetStatus` (`TypedDict`) capturing keys currently used in `data_status[dataset]`:
  - `available: bool`
  - `partial: bool` (currently set via `setdefault` in fetch node)
  - `source: str`
  - `coverage: float`
  - `freshness: float`
  - `error: str | None`
  - optional `by_symbol: dict[str, dict[str, Any]]`
- `DatasetResult` (dataclass or TypedDict) used internally to avoid “mutated locals in nested branches”:
  - `payload: Any` (preserve existing payload shapes)
  - `status: DatasetStatus`

Docstrings must include:

- exact meaning of coverage/freshness
- invariants (e.g. `available=False` implies `error` is set)

#### 2) `policy.py`

Purpose: centralize constants and policy defaults currently duplicated.

Contents:

- `REQUIRED_DATASETS = ("ohlcv", "news", "fundamentals", "macro")`
- thresholds and defaults currently hardcoded:
  - `NEWS_FRESHNESS_THRESHOLD`
  - `DATA_FRESHNESS_THRESHOLD`
  - `FRESHNESS_THRESHOLD` (data_check)

Docstrings should state:

- which node uses each threshold
- why thresholds are separated (if they are)

#### 3) `symbol_resolution.py`

Purpose: unify ticker normalization/variants and ranked symbol match helpers.

Contents:

- `canonicalize_ticker(ticker: str) -> str`
- `ticker_variants(ticker: str) -> list[str]`
- `choose_ranked_symbol_match(...)` and `should_accept_ranked_symbol_match(...)`

Important: preserve current behavior by parameterizing thresholds rather than changing them.

Docstrings must include:

- acceptance thresholds
- ambiguity rules
- exchanges/segments (e.g., `NSE`, `EQ`) used in ranked search

#### 4) `persistence.py`

Purpose: contain the `_store_data()` behavior behind a named API.

Contents:

- `persist_dataset(dataset, payload, ticker, payload_by_symbol) -> PersistOutcome`
- `PersistOutcome` includes:
  - `ok: bool`
  - `error: str | None`
  - optionally `details: dict[str, Any]`

Behavior is preserved by:

- performing the same SQL updates and vector upserts as today
- initially not altering transactional semantics

Docstrings must list:

- for each dataset, which DB methods are invoked
- which cache index keys are written

#### 5) Dataset handlers (`datasets/`)

Purpose: isolate per-dataset logic that is currently spread across branches.

Files:

- `datasets/ohlcv.py`
- `datasets/fundamentals.py`
- `datasets/macro.py`
- `datasets/news.py`

Each handler exposes internal functions used by `data_fetch_node`:

- `materialize_from_local(...) -> DatasetResult`
- `fetch_from_network(...) -> DatasetResult`
- `compute_metrics(...) -> tuple[coverage, freshness]` (if needed)

Docstrings must include:

- expected payload shape returned (exact keys)
- side effects (should be none; persistence handled separately)
- mapping to legacy functions/lines

#### 6) News subpackage (`news/`)

Purpose: consolidate news-specific helpers currently interleaved with general fetch logic.

Files:

- `news/vector_materialize.py`: load from vector DB + convert chunks to article dicts
- `news/metrics.py`: cache summary, coverage/freshness, timestamp parsing
- `news/metadata.py`: build chunk metadata
- `news/dedupe.py`: dedupe key logic

Docstrings must specify:

- required/optional article fields
- freshness semantics and timestamp parsing behavior

### Node Orchestrators (updated, behavior preserved)

#### `data_fetch_node.py`

Responsibilities after refactor:

1. Normalize inputs from `state` (goal/symbols/timeframe policy).
2. Determine `data_plan` (keep current default behavior when empty).
3. For each plan item:
   - merge requirements with timeframe policy (same precedence)
   - attempt materialize if applicable
   - otherwise fetch/refresh
   - compute and record `DatasetStatus` fields exactly as today
   - persist via `persistence.persist_dataset` only when current logic does
4. Build audit entry and finalize output.

Docstring for `data_fetch_node` must include:

- overview of the dataset state machine (materialize → fetch/refresh)
- what gets written to `fetched_data` and `data_status`

#### `data_check_node.py`

Responsibilities after refactor:

1. Validate/narrow `state` boundaries (no assumptions).
2. Resolve ticker locally via symbol resolution.
3. Collect offline evidence (SQL/vector) and merge into `data_status`.
4. Derive missing/stale lists with existing policy.
5. Set next action unchanged.

Docstring must include:

- what “offline audit” means
- evidence sources used

#### `data_plan_node.py`

Responsibilities after refactor:

1. Narrow `data_check`/`timeframe_policy` types defensively.
2. Build `data_plan` items using a shared helper to prevent drift.
3. Keep payload keys and audit behavior stable.

Docstring must include:

- meaning of `P0` vs `P1`

## Testing & Verification Strategy

Behavior-preserving refactors require a strong safety net.

Existing tests already cover many behaviors:

- `backend/tests/unit/test_data_fetch_node_materialization.py`
- `backend/tests/unit/test_autonomous_multi_symbol_flow.py`
- `backend/tests/unit/test_news_cache_reuse.py`
- `backend/tests/unit/test_data_check_node.py`
- `backend/tests/unit/test_data_plan_node.py`

Plan for verification:

1. After each refactor slice, run targeted unit tests for impacted node.
2. Run full unit suite at end: `pytest backend/tests/unit`.
3. Run `ruff check backend/` and `ruff format backend/` only if repo standard requires formatting changes.

Additional tests to add (only when they lock existing behavior):

- Ensure node outputs remain contract-valid.
- Ensure persistence failures are reported in `data_status[dataset]["error"]` without changing output shape.

## Migration Plan (High-Level)

1. Introduce `_types.py` and `policy.py` and update nodes to import constants/types.
2. Extract pure helpers (symbol normalization, parsing, dedupe) into focused modules.
3. Create dataset handler modules and replace per-dataset branching in `data_fetch_node` with handler calls.
4. Move `_store_data` to `persistence.py` and keep semantics identical.
5. Reduce node files to orchestration only.

## Risks & Mitigations

- Risk: accidental payload shape changes.
  - Mitigation: keep old code path outputs in unit tests; compare keys in tests if needed.

- Risk: subtle changes in policy defaults.
  - Mitigation: move constants without changing values; reference original lines in docstrings.

- Risk: event-loop blocking remains.
  - Mitigation: explicitly document in docstrings; isolate IO behind helper functions to enable future async conversion.

## Definition of Done

- Node entrypoints unchanged and behave identically (tests pass).
- Large files reduced to orchestration + imports.
- New internal modules have strong docstrings explaining inputs/outputs/side effects.
- Dead code removed.
