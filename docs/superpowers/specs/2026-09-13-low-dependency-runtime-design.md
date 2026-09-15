# FIN-AI Low-Dependency Runtime Design

## Objective

FIN-AI will remain a CLI-first, human-approved, multi-agent financial research workflow while removing infrastructure and local-model dependencies that do not contribute directly to the demonstrated engineering objective.

The default runtime will require no Docker daemon, database server, vector store, embedding model, GPU runtime, MCP subprocess, or hosted observability SDK.

## Product boundary

The retained workflow is:

```text
request validation
-> clarification and plan approval
-> bounded LangGraph orchestration
-> YFinance structured-data acquisition
-> TinyFish source discovery
-> article extraction
-> deterministic Python quant analysis
-> specialist-agent interpretation
-> counter-thesis critic
-> provenance and policy validation
-> Markdown/JSON run artifact
```

FIN-AI does not execute trades, provide personalized investment advice, predict returns, or claim investment performance.

## Runtime state

LangGraph `ResearchGraphState` is the only mutable runtime state. The existing `fetched_data`, `data_status`, `task_contexts`, `results`, `tool_registry`, and `final_output` fields carry all data needed by a run.

No replacement cache, repository abstraction, SQLite database, or in-memory database will be introduced.

The CLI persists completed or interrupted runs atomically under `.finai/sessions/<session-id>/`. Artifacts contain normalized source metadata, evidence identifiers, provider telemetry, terminal status, and the rendered report. Secrets and authorization headers are excluded.

## Data acquisition

YFinance supplies OHLCV, fundamentals, and macro market series. TinyFish Search discovers current news sources. The existing article extractor downloads and cleans selected pages. PyMuPDF remains the single PDF extractor; duplicate HTML and PDF extraction libraries are removed.

Ticker extraction may use the reasoning model, but acceptance is deterministic: only normalized ticker-shaped candidates are allowed into provider calls. Ambiguous company names cause a clarification request rather than a guessed symbol.

## Evidence handling without RAG

News records are converted directly into `QualitativeEvidenceItem` objects. Each evidence identifier is derived from the canonical URL and captured content hash. Evidence selection is deterministic and bounded by source quality, recency, relevance, deduplication, and task limit.

Offline evaluation uses frozen source snapshots and recorded provider responses. Live TinyFish and YFinance results are diagnostics and are never treated as stable gold labels.

## Agent boundaries

- The planner chooses from an explicit specialist-agent allowlist and a fixed action budget.
- Data acquisition functions fetch and normalize data but do not perform LLM reasoning.
- Quant modules calculate all indicators, ratios, and scores.
- Specialist agents interpret supplied evidence and never call each other.
- The critic searches for unsupported claims, contradictory evidence, and missing downside risks.
- The validator rejects reports with unsupported major claims, mismatched numbers, invalid citations, unsafe advice, or exhausted execution budgets.

## Dependencies

Default runtime dependencies are limited to FastAPI/Uvicorn, HTTPX, Pydantic, LangGraph, YFinance, NumPy, Pandas, PyYAML, json-repair, Trafilatura, and PyMuPDF plus their transitive dependencies.

Development dependencies are pytest, pytest-asyncio, Ruff, and mypy.

The following are removed from the project dependency graph and runtime code: PostgreSQL, TimescaleDB, pgvector, SQLAlchemy, SQLModel, psycopg2, sentence-transformers, Transformers, Torch, NVIDIA CUDA packages, NLTK, MCP, Opik, OpenTelemetry exporters/instrumentation, pdfplumber, newspaper3k, feedparser, rapidfuzz, and pyjson5.

## Failure behavior

- Missing Hive key: stop before model execution with a configuration error.
- Missing TinyFish key: mark news unavailable and continue only when the approved plan does not require news; otherwise terminate as insufficient evidence.
- YFinance timeout or missing data: record the failed dataset and terminate when required coverage cannot be met.
- TinyFish timeout, malformed response, or no results: record the provider failure and do not fabricate qualitative evidence.
- Article extraction failure: retain the snippet with `snippet_only` status and lower evidence quality.
- Conflicting facts: preserve both source references and route to conflict resolution.
- Invalid citation or numeric mismatch: fail validation.
- Planner loop or action-budget exhaustion: terminate with a recorded failure status.

## Evaluation boundary

The controlled benchmark remains local and versioned. RAG metrics are replaced with source-discovery and evidence-selection metrics: source Recall@5/10, MRR@10, evidence coverage, extraction success rate, citation precision/recall, and provider-stage latency.

The benchmark report may publish only measured values. Resume metric fields remain unfilled until a completed benchmark artifact exists.

## Acceptance criteria

1. `uv sync` installs no database, vector, local-model, GPU, MCP, Opik, or OpenTelemetry packages directly or transitively through project-selected features.
2. `uv run pytest` passes after obsolete infrastructure tests are replaced with low-dependency runtime tests.
3. Importing `finai`, `app.main`, and the research graph succeeds without Docker or PostgreSQL.
4. A controlled fixture run reaches a valid terminal status without network access.
5. A live approved CLI run can acquire YFinance and TinyFish evidence, produce citations, and save a scrubbed artifact.
6. Missing, stale, conflicting, and unsafe inputs fail closed.
7. Documentation and evaluation artifacts make no RAG, production-scale, investment-return, or expert-advice claims.
