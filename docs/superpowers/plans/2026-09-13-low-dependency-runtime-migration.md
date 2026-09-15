# FIN-AI Low-Dependency Runtime Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make FIN-AI run its approved multi-agent research workflow without Docker, PostgreSQL, pgvector, RAG, local ML models, GPU libraries, MCP, or third-party observability SDKs.

**Architecture:** Keep LangGraph state as the sole per-run data store. Fetch structured evidence from YFinance and qualitative evidence from TinyFish plus the existing extractor, pass normalized evidence directly to specialist agents, validate provenance, and persist only scrubbed JSON/Markdown CLI artifacts under `.finai/`.

**Tech Stack:** Python 3.12, uv, LangGraph, Hive GLM-5.3-Flash, TinyFish Search, YFinance, HTTPX, Pydantic, NumPy/Pandas, FastAPI/Uvicorn, pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-low-dependency-runtime-design.md`

## Global Constraints

- LLMs never calculate financial ratios, indicators, scores, or forecasts.
- No default runtime dependency may require Docker, PostgreSQL, pgvector, Torch, CUDA, sentence-transformers, Transformers, MCP, Opik, or OpenTelemetry.
- Do not introduce SQLite, a cache service, a repository layer, or another persistence abstraction.
- `ResearchGraphState` remains the sole mutable run state.
- Live provider data is diagnostic; frozen snapshots remain the controlled benchmark source.
- Missing required evidence terminates as insufficient evidence rather than producing a confident report.
- Keep the frontend functional until the CLI replacement is independently accepted.
- Never store API keys, Bearer headers, or full environment dumps in `.finai` artifacts or logs.
- Every task follows red-green-refactor and ends with a focused commit.

---

## Target file structure

### Retained runtime boundaries

- `backend/finai/__main__.py`: interactive CLI and approval loop.
- `backend/app/core/orchestrator.py`: streaming graph execution and run events.
- `backend/app/core/graph/graph_state.py`: complete in-memory run state.
- `backend/app/core/graph/runtime/graph_builder.py`: bounded node graph.
- `backend/app/services/hive_service.py`: model streaming and usage telemetry.
- `backend/data/providers/yfinance.py`: structured live data provider.
- `backend/data/news_pipeline/tinyfish_client.py`: source discovery.
- `backend/data/news_pipeline/extractor.py`: one HTML path and one PDF path.
- `backend/quant/`: deterministic calculations.
- `evals/`: offline evaluation against frozen fixtures.

### Deleted runtime boundaries

- `backend/storage/sql/`: PostgreSQL models, engine, repositories, and client.
- `backend/storage/vector/`: pgvector retrieval implementation.
- `backend/app/services/mcp_service.py`: PostgreSQL MCP subprocess management.
- `backend/app/services/embedding_service.py`: sentence-transformers model lifecycle.
- `backend/agents/financial/data/persistence.py`: database/vector writes.
- `backend/agents/financial/data/news/vector_materialize.py`: vector reads.
- `backend/data/interfaces/storage.py`: unused persistence contracts.
- `backend/quant/nlp_scorer.py`: local FinBERT runtime.
- `backend/docker-compose.yml`: database infrastructure.
- `backend/requirements.txt`: duplicate dependency source after uv migration.

### Modified concepts

- `RetrievalReport` becomes `EvidenceSelectionReport` because no vector retrieval remains.
- `retrieval` fields become `evidence_selection` in task bundles and diagnostics.
- Storage-derived source labels such as `db_load`, `db_check`, and `vector_db_load` become `live_provider`, `run_state`, or `frozen_fixture`.
- Opik decorators/context calls become dependency-free timing/logging helpers named `observe` and `run_context`.

---

### Task 1: Capture the baseline and enforce the dependency boundary

**Files:**
- Create: `backend/tests/unit/test_runtime_dependency_boundary.py`
- Modify: `pyproject.toml`
- Test: `backend/tests/unit/test_runtime_dependency_boundary.py`

**Interfaces:**
- Consumes: project metadata from `pyproject.toml` through Python 3.12 `tomllib`.
- Produces: a regression gate that rejects removed direct dependencies and removed runtime imports.

- [ ] **Step 1: Record the current baseline without changing it**

Run:

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv tree --depth 1
```

Save the exact pass/fail count and direct dependency list in the implementation notes. Existing failures are baseline defects and must not be silently attributed to this migration.

- [ ] **Step 2: Write the failing dependency-boundary test**

```python
from pathlib import Path
import tomllib


FORBIDDEN_DIRECT_DEPENDENCIES = {
    "mcp",
    "nltk",
    "opentelemetry-api",
    "opentelemetry-exporter-otlp",
    "opentelemetry-instrumentation-fastapi",
    "opentelemetry-instrumentation-httpx",
    "opentelemetry-sdk",
    "opik",
    "pdfplumber",
    "pgvector",
    "psycopg2-binary",
    "pyjson5",
    "rapidfuzz",
    "sentence-transformers",
    "sqlalchemy",
    "sqlmodel",
    "torch",
    "transformers",
}


def _dependency_name(requirement: str) -> str:
    return requirement.split("[", 1)[0].split(">", 1)[0].split("=", 1)[0].lower()


def test_default_runtime_has_no_removed_direct_dependencies() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = {
        _dependency_name(item) for item in project["project"]["dependencies"]
    }
    assert dependencies.isdisjoint(FORBIDDEN_DIRECT_DEPENDENCIES)
```

- [ ] **Step 3: Run the test and verify red**

Run:

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_runtime_dependency_boundary.py -v
```

Expected: FAIL listing the currently declared database, local-model, MCP, and observability dependencies.

- [ ] **Step 4: Add import-boundary assertions before pruning dependencies**

Extend the same test file:

```python
FORBIDDEN_RUNTIME_IMPORTS = (
    "storage.sql",
    "storage.vector",
    "app.services.embedding_service",
    "app.services.mcp_service",
)


def test_primary_runtime_files_do_not_import_removed_modules() -> None:
    paths = [
        Path("backend/app"),
        Path("backend/agents"),
        Path("backend/data"),
        Path("backend/finai"),
    ]
    violations: list[str] = []
    for root in paths:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for forbidden in FORBIDDEN_RUNTIME_IMPORTS:
                if forbidden in text:
                    violations.append(f"{path}:{forbidden}")
    assert violations == []
```

Expected: this second test also fails until Tasks 2-9 remove all runtime imports.

- [ ] **Step 5: Commit only the red boundary test**

```bash
git add backend/tests/unit/test_runtime_dependency_boundary.py
git commit -m "test(runtime): define low-dependency boundary"
```

---

### Task 2: Replace hosted observability with local run metrics

**Files:**
- Modify: `backend/app/core/observability.py`
- Modify: `backend/app/config/models.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/orchestrator.py`
- Modify: `backend/agents/orchestration/goal_node.py`
- Modify: `backend/agents/orchestration/router_node.py`
- Modify: `backend/agents/orchestration/validation_node.py`
- Modify: `backend/agents/financial/data/data_check_node.py`
- Modify: `backend/agents/financial/data/data_fetch_node.py`
- Modify: `backend/agents/financial/data/data_plan_node.py`
- Modify: `backend/agents/financial/research/research_context_node.py`
- Modify: `backend/agents/financial/research/research_execution_node.py`
- Modify: `backend/agents/financial/research/research_plan_node.py`
- Modify: `backend/agents/financial/analysis/contrarian.py`
- Modify: `backend/agents/financial/analysis/fundamental.py`
- Modify: `backend/agents/financial/analysis/macro.py`
- Modify: `backend/agents/financial/analysis/sentiment.py`
- Modify: `backend/agents/financial/analysis/technical.py`
- Modify: `backend/agents/quality/claim_verifier.py`
- Modify: `backend/agents/quality/critic_node.py`
- Modify: `backend/agents/quality/evaluator_node.py`
- Modify: `backend/agents/quality/synthesis_node.py`
- Modify: `backend/data/news_pipeline/runner.py`
- Modify: `backend/tests/unit/test_observability.py`
- Modify: `backend/tests/unit/test_observability_config.py`
- Test: `backend/tests/unit/test_observability.py`

**Interfaces:**
- Consumes: existing `@observe(...)` and provider-context update calls.
- Produces: dependency-free timing records through `observe` and `run_context`; `get_recorded_metrics() -> list[dict[str, object]]` for tests and artifacts.

- [ ] **Step 1: Rewrite observability tests to require local timing only**

Test these behaviors:

```python
def test_observe_records_sync_duration():
    clear_recorded_metrics()

    @observe(name="unit.sync")
    def operation():
        return 7

    assert operation() == 7
    metric = get_recorded_metrics()[-1]
    assert metric["name"] == "unit.sync"
    assert metric["status"] == "ok"
    assert metric["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_observe_preserves_async_generator_streaming():
    clear_recorded_metrics()

    @observe(name="unit.stream")
    async def stream():
        yield "a"
        yield "b"

    assert [item async for item in stream()] == ["a", "b"]
    assert get_recorded_metrics()[-1]["name"] == "unit.stream"
```

- [ ] **Step 2: Run the focused tests and verify red**

Run:

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_observability.py backend/tests/unit/test_observability_config.py -v
```

Expected: FAIL because the current implementation delegates to Opik and exposes no local metric buffer.

- [ ] **Step 3: Implement a stdlib-only compatibility layer**

Use `time.perf_counter`, `functools.wraps`, `inspect`, `logging`, and `contextvars.ContextVar`. Preserve sync, coroutine, and async-generator behavior. Store an immutable per-context tuple capped at 1,000 records so concurrent API requests cannot mix telemetry. Context update methods merge metadata into the active run context and must never contact a provider.

Required signatures:

```python
def observe(name: str | None = None, as_type: str = "span", **metadata: object): ...
def get_recorded_metrics() -> list[dict[str, object]]: ...
def clear_recorded_metrics() -> None: ...
```

Expose `run_context.update_current_trace(...)` and `run_context.update_current_span(...)`. Mechanically replace `opik_context` and `langfuse_context` imports/calls in every runtime file listed for this task.

- [ ] **Step 4: Remove hosted-observability configuration and shutdown flushing**

Delete `LANGFUSE_*`, `OPIK_*`, `ENABLE_OBSERVABILITY`, and OTLP settings from `EnvSettings`. Remove the `get_langfuse().flush()` shutdown branch from `app.main`.

- [ ] **Step 5: Run focused tests**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_observability.py backend/tests/unit/test_observability_config.py backend/tests/unit/test_orchestrator_node_trace_logging.py -v
```

Expected: PASS with no Opik network initialization or warning output.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/observability.py backend/app/config/models.py backend/app/main.py backend/app/core/orchestrator.py backend/agents backend/data/news_pipeline/runner.py backend/tests/unit/test_observability.py backend/tests/unit/test_observability_config.py
git commit -m "refactor(runtime): replace hosted tracing with local metrics"
```

---

### Task 3: Remove database and MCP startup requirements

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/routes/health.py`
- Modify: `backend/app/core/node_resources.py`
- Delete: `backend/app/services/mcp_service.py`
- Modify: `backend/tests/unit/test_health_route.py`
- Modify: `backend/tests/unit/test_node_resources.py`

**Interfaces:**
- Consumes: `HiveService`, `TinyFishSearchClient`, and `YFinanceFetcher`.
- Produces: API startup with no subprocesses; health payload reporting only `hive`, `tinyfish`, and `yfinance` configuration/readiness.

- [ ] **Step 1: Write health tests for the new component set**

```python
@pytest.mark.asyncio
async def test_health_has_no_database_or_embedding_components(monkeypatch):
    monkeypatch.setattr(health, "_check_yfinance_readiness", lambda: True)
    monkeypatch.setattr(health, "_run_external_canary", _successful_canary)
    payload = await health.health_check(llm_service=_HealthyLLM())
    assert payload["components"] == {
        "llm_service": "up",
        "llm_provider": "hive",
        "tinyfish_search": "up",
        "market_data": "up",
    }
```

Also assert application lifespan does not import or start an MCP manager.

- [ ] **Step 2: Verify red**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_health_route.py backend/tests/unit/test_node_resources.py -v
```

Expected: FAIL because database, embedding, and MCP resources still exist.

- [ ] **Step 3: Reduce `NodeResources`**

Keep only lazy properties:

```python
@property
def llm_service(self) -> HiveService: ...

@property
def yf_fetcher(self) -> YFinanceFetcher: ...
```

Remove `sql_db` and `vector_db` state and properties.

- [ ] **Step 4: Simplify API lifespan and health**

Use a no-op lifespan or remove the custom lifespan entirely if FastAPI needs no startup/shutdown work. Health must not make a paid Hive generation request; Hive readiness means key/configuration present. TinyFish external canary remains explicitly diagnostic.

- [ ] **Step 5: Delete the MCP service**

Delete `backend/app/services/mcp_service.py` after `rg -n "mcp_manager|mcp_service" backend` shows no remaining callers.

- [ ] **Step 6: Verify**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_health_route.py backend/tests/unit/test_node_resources.py -v
UV_CACHE_DIR=/tmp/fin-ai-uv-cache PYTHONPATH=backend uv run python -c "from app.main import app; print(app.title)"
```

Expected: tests PASS and FastAPI imports without a database server.

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/app/routes/health.py backend/app/core/node_resources.py backend/app/services/mcp_service.py backend/tests/unit/test_health_route.py backend/tests/unit/test_node_resources.py
git commit -m "refactor(runtime): remove database and MCP startup"
```

---

### Task 4: Make ticker resolution deterministic and database-free

**Files:**
- Modify: `backend/app/core/instrument_resolver.py`
- Modify: `backend/agents/orchestration/goal_node.py`
- Modify: `backend/tests/unit/test_instrument_resolver.py`
- Modify: `backend/tests/unit/test_goal_ticker_extraction.py`

**Interfaces:**
- Consumes: model-produced ticker candidates plus optional exchange hints.
- Produces: `resolve_instruments(...) -> ResolutionResult` with `resolver_source="deterministic_candidate"`; unresolved names route to clarification.

- [ ] **Step 1: Replace database-resolution expectations with deterministic acceptance tests**

Cover:

```python
def test_resolves_valid_nse_ticker_without_storage():
    result = resolve_instruments("Analyze INFY", ["INFY"], exchange_hint="NSE")
    assert result.primary_instrument.trading_symbol == "INFY"
    assert result.primary_instrument.instrument_key == "NSE_EQ:INFY"
    assert result.resolver_source == "deterministic_candidate"


def test_rejects_company_name_that_is_not_a_ticker():
    result = resolve_instruments("Analyze HDFC Bank", ["HDFC Bank"])
    assert result.primary_instrument is None
    assert result.unresolved_entities == ["HDFC Bank"]
```

Also cover `.NS`, `.BO`, numeric BSE codes, invalid punctuation, empty candidates, and multiple valid candidates.

- [ ] **Step 2: Verify red**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_instrument_resolver.py backend/tests/unit/test_goal_ticker_extraction.py -v
```

- [ ] **Step 3: Rewrite resolver internals**

Remove `PostgresClient`. Normalize with existing ticker utilities and regex rules. Construct `ResolvedInstrument` directly only when a candidate is ticker-shaped. Do not infer a symbol from a company name. Preserve ambiguity/unresolved lists so `goal_node` can request human input.

- [ ] **Step 4: Update goal audit vocabulary**

Replace `db_lookup` with `deterministic_candidate`. Ensure approval follows successful normalization and ambiguity still yields `awaiting_clarification`.

- [ ] **Step 5: Verify**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_instrument_resolver.py backend/tests/unit/test_goal_ticker_extraction.py backend/tests/core/test_ticker.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/instrument_resolver.py backend/agents/orchestration/goal_node.py backend/tests/unit/test_instrument_resolver.py backend/tests/unit/test_goal_ticker_extraction.py
git commit -m "refactor(agent): resolve ticker candidates without storage"
```

---

### Task 5: Convert data checking and planning to run-state checks

**Files:**
- Modify: `backend/agents/financial/data/data_check_node.py`
- Modify: `backend/agents/financial/data/data_plan_node.py`
- Modify: `backend/agents/financial/data/status_merge.py`
- Modify: `backend/app/core/orchestration_schemas.py`
- Modify: `backend/tests/unit/test_data_check_node.py`
- Modify: `backend/tests/unit/test_data_plan_node.py`
- Modify: `backend/tests/unit/test_data_status_merge.py`

**Interfaces:**
- Consumes: `state["fetched_data"]`, `state["data_status"]`, normalized ticker, and timeframe policy.
- Produces: required dataset statuses and a bounded list of `fetch` operations; never emits `materialize` or storage lookup operations.

- [ ] **Step 1: Add failing run-state tests**

Required cases:

```python
@pytest.mark.asyncio
async def test_initial_data_check_marks_provider_datasets_missing():
    output = await data_check_node(_state(ticker="INFY", fetched_data={}))
    assert set(output["data_check"]["missing_datasets"]) == {
        "ohlcv", "fundamentals", "news", "macro"
    }
    assert output["next_action"] == "run_data_plan"


@pytest.mark.asyncio
async def test_data_check_accepts_complete_run_state_without_storage():
    output = await data_check_node(_complete_state())
    assert output["data_check"]["missing_datasets"] == []
    assert output["next_action"] == "run_research_plan"
```

Add stale, malformed, partial, and missing-ticker cases.

- [ ] **Step 2: Verify red**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_data_check_node.py backend/tests/unit/test_data_plan_node.py backend/tests/unit/test_data_status_merge.py -v
```

- [ ] **Step 3: Rewrite data checking**

Delete `_news_info_for_ticker`, `_resolve_local_symbol`, `_build_deterministic_offline_status`, and every `resources.sql_db`/`resources.vector_db` call. Determine readiness solely from normalized run-state status and payload shape.

- [ ] **Step 4: Simplify planning**

For each missing or stale required dataset, create exactly one operation:

```python
{
    "dataset": dataset,
    "action": "fetch",
    "priority": "P0",
    "requirements": timeframe_policy.get(dataset, {}),
}
```

Deduplicate by dataset and cap operations at the number of required datasets.

- [ ] **Step 5: Rename storage-specific schema descriptions and source values**

Change database language to provider/run-state language. Allowed sources are `run_state`, `live_provider`, and `frozen_fixture`.

- [ ] **Step 6: Verify**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_data_check_node.py backend/tests/unit/test_data_plan_node.py backend/tests/unit/test_data_status_merge.py backend/tests/unit/test_graph_data_freshness.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/agents/financial/data/data_check_node.py backend/agents/financial/data/data_plan_node.py backend/agents/financial/data/status_merge.py backend/app/core/orchestration_schemas.py backend/tests/unit/test_data_check_node.py backend/tests/unit/test_data_plan_node.py backend/tests/unit/test_data_status_merge.py
git commit -m "refactor(data): check evidence from graph state"
```

---

### Task 6: Make data fetching online-only and non-persistent

**Files:**
- Modify: `backend/agents/financial/data/data_fetch_node.py`
- Modify: `backend/agents/financial/data/datasets/ohlcv.py`
- Modify: `backend/agents/financial/data/datasets/fundamentals.py`
- Modify: `backend/agents/financial/data/datasets/macro.py`
- Modify: `backend/agents/financial/data/datasets/news.py`
- Delete: `backend/agents/financial/data/persistence.py`
- Delete: `backend/agents/financial/data/news/vector_materialize.py`
- Replace: `backend/tests/unit/test_data_fetch_node_materialization.py` with `backend/tests/unit/test_data_fetch_node_live.py`
- Modify: `backend/tests/unit/test_autonomous_multi_symbol_flow.py`

**Interfaces:**
- Consumes: `data_plan` fetch operations and provider clients exposed through `resources`.
- Produces: normalized `fetched_data` and `data_status` in graph state; no side effects beyond provider requests.

- [ ] **Step 1: Write failing online-only fetch tests**

Inject stub YFinance and TinyFish/news runner objects. Assert:

```python
@pytest.mark.asyncio
async def test_fetch_node_keeps_payloads_in_state_without_persistence(monkeypatch):
    output = await data_fetch_node(_fetch_state())
    assert output["fetched_data"]["ohlcv"]["by_symbol"]["INFY"]
    assert output["fetched_data"]["fundamentals"]["by_symbol"]["INFY"]
    assert output["fetched_data"]["news"]
    assert output["data_status"]["news"]["source"] == "live_provider"
```

Add tests for one provider timeout, empty OHLCV, malformed fundamentals, no news, and partial multi-symbol results. Assert each failure is represented in `data_status` and never replaced by fabricated data.

- [ ] **Step 2: Verify red**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_data_fetch_node_live.py backend/tests/unit/test_autonomous_multi_symbol_flow.py -v
```

- [ ] **Step 3: Remove materialization paths**

Delete `_build_materialize_plan`, `_required_status_ready_for_materialization`, `_required_payloads_materialized`, SQL loader wrappers, `materialize_dataset`, `persist_dataset_result`, `_store_data`, and `should_persist` from result types.

- [ ] **Step 4: Retain one fetch function per dataset**

Required calls:

```python
fetch_ohlcv_by_symbol(symbols, requirements)
fetch_fundamentals_by_symbol(symbols, requirements)
fetch_macro_dataset(requirements)
await fetch_planned_news(...)
```

Every successful result uses `source="live_provider"`. Every exception is caught at the dataset boundary and records `available=False`, `error=<categorized message>`, and the unchanged action budget.

- [ ] **Step 5: Remove SQL loaders from dataset modules**

Keep only coverage and provider-fetch functions in OHLCV, fundamentals, and macro modules. In news, remove `materialize_news_dataset` and the vector import.

- [ ] **Step 6: Delete persistence and vector materialization modules**

Before deletion, run:

```bash
rg -n "persist_dataset|vector_materialize|load_news_from_vector_db|materialize_.*dataset|load_.*_from_sql" backend --glob '*.py'
```

Expected: only the files being deleted or tests being replaced remain.

- [ ] **Step 7: Verify**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_data_fetch_node_live.py backend/tests/unit/test_news_pipeline_runner.py backend/tests/unit/test_news_yield_resilience.py backend/tests/unit/test_autonomous_multi_symbol_flow.py -v
```

- [ ] **Step 8: Commit**

```bash
git add backend/agents/financial/data backend/tests/unit/test_data_fetch_node_live.py backend/tests/unit/test_autonomous_multi_symbol_flow.py
git commit -m "refactor(data): keep fetched evidence in graph state"
```

---

### Task 7: Replace RAG context assembly with deterministic evidence selection

**Files:**
- Modify: `backend/app/core/research_plan_schemas.py`
- Modify: `backend/agents/financial/research/context_assembly.py`
- Modify: `backend/agents/financial/research/research_context_node.py`
- Modify: `backend/agents/financial/research/query_derivation.py`
- Replace: `backend/tests/unit/test_rag_hardening.py` with `backend/tests/unit/test_evidence_selection.py`
- Modify: `backend/tests/unit/test_research_context_node.py`

**Interfaces:**
- Consumes: normalized news records in `fetched_data["news"]` and each task's qualitative requirements.
- Produces: `EvidenceSelectionReport` and bounded `QualitativeEvidenceItem` values with stable evidence IDs.

- [ ] **Step 1: Define failing evidence-selection tests**

Test that selection:

- rejects records without URL and usable text;
- deduplicates canonical URLs;
- filters by ticker/company relevance;
- orders trusted, recent, complete records first;
- enforces `requirements.limit`;
- creates the same evidence ID for the same canonical URL and content;
- returns `failure_reason="no_relevant_evidence"` when empty.

Example assertion:

```python
execution_input = build_execution_input(task, fetched_data, data_status)
items = execution_input.evidence_bundle.qualitative_inputs
assert items[0].evidence_id.startswith("news:")
assert items[0].metadata["canonical_url"] == "https://example.com/infy-results"
assert execution_input.evidence_bundle.evidence_selection.source == "live_news"
```

- [ ] **Step 2: Verify red**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_evidence_selection.py backend/tests/unit/test_research_context_node.py -v
```

- [ ] **Step 3: Rename the schema**

Define:

```python
class EvidenceSelectionReport(BaseModel):
    query_text: str = ""
    limit: int = 0
    requested_source_types: list[str] = Field(default_factory=list)
    returned_count: int = 0
    source: str = "none"
    failure_reason: str | None = None
```

Replace `AgentEvidenceBundle.retrieval` with `evidence_selection`. Do not retain a deprecated alias because all consumers are in this repository.

- [ ] **Step 4: Implement deterministic selection**

Use existing URL canonicalization, source quality, recency, and deduplication helpers. Use SHA-256 over `canonical_url + "\n" + selected_text` for evidence IDs. Include title, snippet, extracted content, published date, source domain, extraction status, canonical URL, and content hash in metadata.

- [ ] **Step 5: Remove embedding/vector calls**

Delete `_vector_items`, `EmbeddingService`, and `resources.vector_db` usage. `build_execution_input` reads only its explicit arguments.

- [ ] **Step 6: Update diagnostics**

Rename `retrieval_diagnostics` to `evidence_selection_diagnostics` in node output and audit records.

- [ ] **Step 7: Verify**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_evidence_selection.py backend/tests/unit/test_research_context_node.py backend/tests/unit/test_research_execution_contracts.py backend/tests/unit/test_graph_evidence_extraction.py -v
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/research_plan_schemas.py backend/agents/financial/research backend/tests/unit/test_evidence_selection.py backend/tests/unit/test_research_context_node.py
git commit -m "refactor(research): select evidence without vector retrieval"
```

---

### Task 8: Remove database and retrieval tools from the planner surface

**Files:**
- Modify: `backend/app/core/tools/tool_system.py`
- Modify: `backend/app/core/graph/router_policy.py`
- Modify: `backend/config/prompts/market_offline.yaml`
- Modify: `backend/config/prompts/autonomous_orchestrator.yaml`
- Modify: `backend/tests/unit/test_tool_system.py`
- Modify: `backend/tests/unit/test_tool_registry.py`
- Modify: `backend/tests/unit/test_graph_router_policy.py`

**Interfaces:**
- Consumes: in-state provider payloads supplied to deterministic analysis handlers.
- Produces: a planner allowlist containing only acquisition, deterministic analysis, submission, critic, and validation actions.

- [ ] **Step 1: Write failing allowlist tests**

```python
def test_registry_exposes_no_storage_or_rag_tools():
    names = {tool.full_name for tool in tool_registry.get_all_tools()}
    forbidden = {
        "market:check_db_status",
        "market:get_table_names",
        "market:get_column_names",
        "market:get_ticker_info",
        "market:get_fundamentals_info",
        "market:get_macro_info",
        "market:get_news_info",
        "market:resolve_instrument_exact",
        "market:search_instruments",
        "market:get_derivative_chain",
        "market:submit_offline_status",
        "news:search_vector_db",
        "retrieval:submit_retrieval_results",
    }
    assert names.isdisjoint(forbidden)
```

Also assert disallowed planner actions fail before execution and still count toward the action budget.

- [ ] **Step 2: Verify red**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_tool_system.py backend/tests/unit/test_tool_registry.py backend/tests/unit/test_graph_router_policy.py -v
```

- [ ] **Step 3: Remove storage/retrieval tool definitions and handlers**

Keep deterministic scan handlers and delegation markers used by the graph. Remove `ToolNamespace.RETRIEVAL` if no registered tool uses it. Remove the local `PostgresClient` import and `_handle_get_news_info`.

- [ ] **Step 4: Update planner prompts**

Prompts must instruct the planner that evidence is fetched once into run state. Remove database inspection, vector search, cache materialization, derivative-chain, and offline-status language. Preserve strict JSON action schemas and allowlists.

- [ ] **Step 5: Simplify router readiness terminology**

Rename `_required_payloads_materialized` to `_required_payloads_present`. Keep retry and termination behavior unchanged.

- [ ] **Step 6: Verify**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_tool_system.py backend/tests/unit/test_tool_registry.py backend/tests/unit/test_tool_result_contract.py backend/tests/unit/test_graph_router_policy.py backend/tests/unit/test_autonomous_runtime_flow.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/tools/tool_system.py backend/app/core/graph/router_policy.py backend/config/prompts backend/tests/unit/test_tool_system.py backend/tests/unit/test_tool_registry.py backend/tests/unit/test_graph_router_policy.py
git commit -m "refactor(agent): remove storage and RAG tools"
```

---

### Task 9: Make provenance artifacts complete and secret-safe

**Files:**
- Modify: `backend/finai/__main__.py`
- Modify: `backend/app/core/orchestrator.py`
- Modify: `backend/app/models/response_models.py`
- Create: `backend/tests/unit/test_cli_run_artifacts.py`
- Modify: `backend/tests/unit/test_orchestrator_streaming_safety.py`

**Interfaces:**
- Consumes: final graph payload, stream events, Hive telemetry, and selected evidence metadata.
- Produces: atomic run JSON with `run_id`, `session_id`, request, plan, terminal status, evidence manifest, report, provider metrics, errors, configuration fingerprint, and timestamps.

- [ ] **Step 1: Write failing artifact tests**

Use `tmp_path` and a fake orchestrator. Assert the saved payload contains:

```python
assert artifact["terminal_status"] == "validated"
assert artifact["evidence_manifest"][0]["evidence_id"].startswith("news:")
assert artifact["provider_metrics"][0]["provider"] == "hive"
assert artifact["report"]
```

Recursively scan serialized output and assert it contains none of the configured key values, `Authorization`, `Bearer`, or `X-API-Key`.

- [ ] **Step 2: Verify red**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_cli_run_artifacts.py backend/tests/unit/test_orchestrator_streaming_safety.py -v
```

- [ ] **Step 3: Extend the final stream payload**

Expose selected evidence metadata and Hive telemetry as structured fields. Do not include full request headers or environment values.

- [ ] **Step 4: Extend `_write_run` atomically**

Keep the existing temporary-file plus `replace` pattern. Add a recursive redaction function that removes keys matching `api_key`, `authorization`, `secret`, and `token` except numeric usage fields such as `input_tokens` and `output_tokens`.

- [ ] **Step 5: Write Markdown beside JSON**

Save `<run-id>.md` containing terminal status, evidence-linked report, limitations, and failure details. JSON remains the machine-readable source of truth.

- [ ] **Step 6: Verify**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_cli_run_artifacts.py backend/tests/unit/test_orchestrator_streaming_safety.py backend/tests/unit/test_orchestrator_persistent_jsonl_logging.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/finai backend/app/core/orchestrator.py backend/app/models/response_models.py backend/tests/unit/test_cli_run_artifacts.py backend/tests/unit/test_orchestrator_streaming_safety.py
git commit -m "feat(cli): persist provenance-complete run artifacts"
```

---

### Task 10: Remove local NLP and duplicate extraction dependencies

**Files:**
- Delete: `backend/quant/nlp_scorer.py`
- Delete: `backend/app/services/embedding_service.py`
- Delete: `backend/data/processors/text.py`
- Modify: `backend/data/news_pipeline/extractor.py`
- Modify: `backend/data/news_pipeline/normalize.py`
- Delete: `backend/tests/unit/test_embedding_service_ttl.py`
- Modify: `backend/tests/unit/test_news_pipeline_extractor.py`
- Modify: `backend/tests/unit/test_news_pipeline_dedupe.py`

**Interfaces:**
- Consumes: article URL/snippet and normalized news records.
- Produces: HTML extraction through Trafilatura, PDF extraction through PyMuPDF, and stdlib fuzzy-title comparison through `difflib.SequenceMatcher`.

- [ ] **Step 1: Add failing extractor-boundary tests**

Assert that HTML extraction tries Trafilatura then returns `snippet_only`; PDF extraction uses only `_extract_with_pymupdf`; and deduplication uses the stdlib path deterministically.

- [ ] **Step 2: Verify red**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_news_pipeline_extractor.py backend/tests/unit/test_news_pipeline_dedupe.py -v
```

- [ ] **Step 3: Remove duplicate extraction paths**

Delete `_extract_with_newspaper` and `_extract_with_pdfplumber`. Remove `io` only if PyMuPDF no longer needs it. Keep the existing paywall, relevance, word-count, and snippet fallback behavior.

- [ ] **Step 4: Use stdlib title similarity**

Replace the conditional RapidFuzz import with the existing normalized `SequenceMatcher` calculation directly.

- [ ] **Step 5: Remove local-model modules**

Verify no runtime callers remain, then delete `nlp_scorer.py`, `embedding_service.py`, and vector-oriented `data/processors/text.py`. Replace any remaining sentiment path with LLM interpretation over supplied evidence; it must not claim deterministic FinBERT scoring.

- [ ] **Step 6: Verify**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_news_pipeline_extractor.py backend/tests/unit/test_news_pipeline_dedupe.py backend/tests/unit/test_sentiment_analysis_node.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/quant/nlp_scorer.py backend/app/services/embedding_service.py backend/data/processors/text.py backend/data/news_pipeline backend/tests/unit/test_news_pipeline_extractor.py backend/tests/unit/test_news_pipeline_dedupe.py backend/tests/unit/test_embedding_service_ttl.py
git commit -m "refactor(runtime): remove local ML and duplicate extractors"
```

---

### Task 11: Delete storage infrastructure and obsolete tests

**Files:**
- Delete: `backend/storage/sql/`
- Delete: `backend/storage/vector/`
- Delete: `backend/data/interfaces/storage.py`
- Delete: `backend/docker-compose.yml`
- Delete: `backend/tests/unit/test_memory_models.py`
- Delete: `backend/tests/unit/test_pgvector_storage.py`
- Delete: `backend/tests/unit/test_sql_client_save_ohlcv.py`
- Delete: `backend/tests/unit/test_sql_instrument_client.py`
- Delete: `backend/tests/unit/test_sql_models.py`
- Delete: `backend/tests/unit/test_sql_repo_boundaries.py`
- Delete: `backend/tests/unit/test_sql_text_chunk_schema.py`
- Delete: `backend/tests/unit/test_sql_ticker_helpers.py`
- Modify: `backend/tests/unit/test_ticker_normalization_guard.py`

**Interfaces:**
- Consumes: successful completion of Tasks 3-10.
- Produces: a repository with no storage implementation or tests for removed behavior.

- [ ] **Step 1: Prove the deleted code has no runtime callers**

Run:

```bash
rg -n "storage\.sql|storage\.vector|PostgresClient|PgVectorStorage|IStructuredStorage|IVectorStorage|DATABASE_URL|POSTGRES_" backend --glob '*.py'
```

Expected: matches occur only inside the deletion targets and obsolete tests. If another runtime caller appears, remove that caller in its owning earlier task before continuing.

- [ ] **Step 2: Delete exact storage and infrastructure targets**

Use patch-based deletions. Do not delete `backend/storage/` if it contains unrelated user files; remove only `sql`, `vector`, and their now-empty package files.

- [ ] **Step 3: Delete tests whose product behavior no longer exists**

Delete only database schema/repository/vector tests listed above. Preserve ticker normalization, provider, graph, quant, evidence, safety, and artifact tests.

- [ ] **Step 4: Remove PostgreSQL settings**

Delete `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT`, and `DATABASE_URL` from `EnvSettings`.

- [ ] **Step 5: Verify import and test collection**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest --collect-only -q
UV_CACHE_DIR=/tmp/fin-ai-uv-cache PYTHONPATH=backend uv run python -c "from finai.__main__ import FinAIRepl; from app.main import app; from app.core.graph.runtime.graph_builder import build_graph; print('imports-ok')"
```

Expected: collection and imports succeed without SQL packages installed.

- [ ] **Step 6: Commit**

```bash
git add backend/storage backend/data/interfaces/storage.py backend/docker-compose.yml backend/app/config/models.py backend/tests/unit
git commit -m "refactor(storage): remove database and vector infrastructure"
```

---

### Task 12: Prune and lock the uv dependency graph

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Delete: `backend/requirements.txt`
- Test: `backend/tests/unit/test_runtime_dependency_boundary.py`

**Interfaces:**
- Consumes: runtime imports after Tasks 2-11.
- Produces: one authoritative uv dependency graph.

- [ ] **Step 1: Replace runtime dependencies with the exact minimal set**

```toml
dependencies = [
    "fastapi",
    "httpx",
    "json-repair>=0.58.0",
    "langgraph>=0.2.0",
    "numpy",
    "pandas",
    "pydantic>=2.0.0",
    "pydantic-settings",
    "pymupdf",
    "pyyaml",
    "trafilatura",
    "uvicorn",
    "yfinance",
]
```

Keep the existing development group containing only `mypy`, `pytest`, `pytest-asyncio`, and `ruff`.

- [ ] **Step 2: Remove duplicate dependency metadata**

Delete `backend/requirements.txt`. Update operational documentation in Task 13 so all commands use `uv sync` and `uv run`.

- [ ] **Step 3: Regenerate the lockfile**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv lock
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv sync --refresh
```

- [ ] **Step 4: Verify forbidden packages are absent**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_runtime_dependency_boundary.py -v
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv tree | rg "torch|nvidia-|sentence-transformers|transformers|sqlalchemy|sqlmodel|pgvector|psycopg2|opik|opentelemetry|mcp"
```

Expected: dependency-boundary test PASS; the `uv tree` filter returns no matches. If a forbidden package remains transitively, inspect `uv tree --invert <package>` and remove or replace its parent only when that parent is not required by the retained runtime.

- [ ] **Step 5: Verify environment size for evidence**

```bash
du -sh .venv
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv tree --depth 1
```

Record the measured environment size and direct dependency count before and after migration in `docs/benchmark-report.md`; do not describe the reduction without those values.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock backend/requirements.txt backend/tests/unit/test_runtime_dependency_boundary.py
git commit -m "build(uv): lock minimal FIN-AI runtime"
```

---

### Task 13: Align evaluation with source discovery rather than RAG

**Files:**
- Modify: `docs/evaluation-design.md`
- Modify: `docs/benchmark-report.md`
- Modify: `evals/metrics.py`
- Modify: `evals/run.py`
- Modify: `backend/tests/unit/test_evaluation_metrics.py`
- Modify: `backend/tests/unit/test_evaluation_runner.py`

**Interfaces:**
- Consumes: frozen source snapshots, recorded TinyFish responses, evidence manifests, and run results.
- Produces: deterministic source-discovery, extraction, citation, agent, safety, latency, and cost metrics.

- [ ] **Step 1: Write failing metric tests**

Add exact fixtures for:

```python
def test_source_discovery_metrics():
    metrics = source_discovery_metrics(
        returned_ids=["s2", "s1", "s4"],
        relevant_ids={"s1", "s3"},
        k_values=(1, 3),
    )
    assert metrics["recall_at_1"] == 0.0
    assert metrics["recall_at_3"] == 0.5
    assert metrics["mrr_at_10"] == 0.5


def test_extraction_success_rate_counts_full_and_partial_only():
    assert extraction_success_rate(["full", "partial", "snippet_only", "failed"]) == 0.5
```

- [ ] **Step 2: Verify red**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_evaluation_metrics.py backend/tests/unit/test_evaluation_runner.py -v
```

- [ ] **Step 3: Replace RAG metrics**

Remove dense/hybrid/reranking variant fields and vector retrieval metrics. Add source Recall@5/10, MRR@10, evidence coverage, extraction success, snippet-fallback rate, citation precision/recall, provider failure rate, and per-stage latency.

- [ ] **Step 4: Preserve benchmark truthfulness**

Keep `evals/gold/v1/tasks.jsonl` empty until authored labels and frozen snapshots exist. Benchmark output must remain `insufficient_evidence` rather than emitting zero-valued performance claims.

- [ ] **Step 5: Update ablations**

Use these controlled variants on the same frozen cases:

1. quant-only;
2. single synthesis agent;
3. multi-agent without critic;
4. multi-agent without validation gate;
5. full bounded multi-agent workflow.

- [ ] **Step 6: Verify**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_evaluation_metrics.py backend/tests/unit/test_evaluation_runner.py -v
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run python -m evals.run --gold evals/gold/v1/tasks.jsonl --results evals/results/local.json
```

Expected: tests PASS; empty gold set reports insufficient evidence and does not claim benchmark scores.

- [ ] **Step 7: Commit**

```bash
git add docs/evaluation-design.md docs/benchmark-report.md evals backend/tests/unit/test_evaluation_metrics.py backend/tests/unit/test_evaluation_runner.py
git commit -m "refactor(evals): measure evidence discovery without RAG"
```

---

### Task 14: Update architecture, governance, and run documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/decisions.md`
- Modify: `docs/failure-taxonomy.md`
- Modify: `ai_engineering/PROJECT_CONSTITUTION.md`
- Modify: `ai_engineering/AGENT_RULES.md`
- Modify: `ai_engineering/ARCHITECTURE_DECISIONS.md`
- Modify: `AGENTS.md`
- Modify: `.env.example`

**Interfaces:**
- Consumes: verified runtime commands and final architecture.
- Produces: one consistent project description with no claims about removed infrastructure or unavailable benchmarks.

- [ ] **Step 1: Update architecture language**

The canonical flow must read:

```text
CLI/frontend -> approval -> bounded graph -> YFinance/TinyFish
-> deterministic quant -> specialist agents -> critic -> provenance gate
-> .finai artifacts
```

Remove PostgreSQL, TimescaleDB, pgvector, embeddings, RAG, local inference, FinBERT, Docker, MCP, Opik, and OpenTelemetry from current architecture claims.

- [ ] **Step 2: Update environment and run commands**

Document only:

```bash
uv sync
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest
UV_CACHE_DIR=/tmp/fin-ai-uv-cache PYTHONPATH=backend uv run python -m finai
UV_CACHE_DIR=/tmp/fin-ai-uv-cache PYTHONPATH=backend uv run uvicorn app.main:app --reload --port 8000
```

`.env.example` contains replacement markers for Hive and TinyFish only, plus non-secret timeout/model settings. Do not include real key-shaped values.

- [ ] **Step 3: Record the architecture decision**

Add a dated decision explaining that persistent/vector infrastructure was removed because the project demonstrates reliable agent workflow engineering rather than multi-user data serving. Record the trade-off: each live run refetches evidence and cross-run semantic search is unavailable.

- [ ] **Step 4: Update failure taxonomy**

Replace database/vector failures with provider timeout, malformed provider response, no relevant sources, extraction failure, conflicting evidence, invalid citation, unsafe request, and budget exhaustion.

- [ ] **Step 5: Scan for stale claims**

```bash
rg -n -i "postgres|timescale|pgvector|vector db|vector database|embedding|rag|docker|llama|finbert|torch|cuda|nvidia|mcp|opik|opentelemetry|exa" README.md docs ai_engineering AGENTS.md backend --glob '!*.pyc'
```

Expected: no current architecture claim or runtime import remains. Historical decision text may mention removed components only when explicitly marked as removed.

- [ ] **Step 6: Commit**

```bash
git add README.md docs ai_engineering AGENTS.md .env.example
git commit -m "docs: describe low-dependency FIN-AI runtime"
```

---

### Task 15: Full regression, offline smoke, and one approved live smoke

**Files:**
- Modify only files required to fix migration-caused failures.
- Create: `evals/results/low-dependency-smoke.json` only from a controlled fixture run.

**Interfaces:**
- Consumes: completed Tasks 1-14.
- Produces: verification evidence for local correctness and a separately identified live diagnostic.

- [ ] **Step 1: Run formatting and static checks**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run ruff format --check backend evals
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run ruff check backend evals
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run mypy backend
```

Fix only failures caused by this migration. Record unrelated baseline failures separately rather than broad-refactoring them.

- [ ] **Step 2: Run the complete backend suite**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest
```

Expected: zero collection errors and zero failing tests.

- [ ] **Step 3: Run import and dependency gates**

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache PYTHONPATH=backend uv run python -c "from finai.__main__ import FinAIRepl; from app.main import app; from app.core.graph.runtime.graph_builder import build_graph; build_graph(); print('runtime-ok')"
UV_CACHE_DIR=/tmp/fin-ai-uv-cache uv run pytest backend/tests/unit/test_runtime_dependency_boundary.py -v
git diff --check
```

- [ ] **Step 4: Run a frozen offline workflow fixture**

Use injected YFinance, TinyFish, extractor, and Hive fixtures. Assert the graph reaches `validated`, all numeric claims match fixture quant outputs, every major claim has evidence, and the artifact is secret-free. Save only the fixture result to `evals/results/low-dependency-smoke.json`.

- [ ] **Step 5: Request explicit approval for one live provider run**

Explain that the run contacts Hive, TinyFish, YFinance, and public source pages and may incur Hive usage. After approval, run:

```bash
UV_CACHE_DIR=/tmp/fin-ai-uv-cache PYTHONPATH=backend uv run python -m finai
```

Use one bounded request such as `Assess downside risks for INFY over six months`, review the proposed plan, approve it, and verify the resulting `.finai` JSON/Markdown artifact.

- [ ] **Step 6: Report verification layers separately**

Final handoff must separate:

- local deterministic tests and static checks;
- frozen offline workflow result;
- live provider diagnostic result;
- unexecuted 100-case benchmark and unverified resume metrics.

- [ ] **Step 7: Commit final verification artifact and fixes**

```bash
git add backend evals/results/low-dependency-smoke.json
git commit -m "test(runtime): verify low-dependency research workflow"
```

---

## Migration completion checklist

- [ ] No default runtime import references PostgreSQL, pgvector, embeddings, local NLP models, MCP, Opik, or OpenTelemetry.
- [ ] `pyproject.toml` is the sole Python dependency source.
- [ ] `uv.lock` contains no removed package through a retained project dependency.
- [ ] API and CLI import without Docker or database services.
- [ ] Ticker ambiguity requests human clarification.
- [ ] Every dataset failure is visible in graph state and artifacts.
- [ ] Evidence IDs are stable for frozen content.
- [ ] Numeric provenance and citation gates remain fail-closed.
- [ ] Run artifacts redact credentials and authorization data.
- [ ] Controlled evaluation remains separate from live diagnostics.
- [ ] README contains no unmeasured benchmark or production-scale claim.
- [ ] Resume bullets remain unfilled until measured benchmark results exist.
