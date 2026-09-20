# FIN-AI

FIN-AI is a CLI-first, human-in-the-loop financial research workflow for NSE/BSE equities. It combines deterministic Python quant analysis with Hive GLM-5.3-Flash, YFinance market data, TinyFish web search, source extraction, citation checks, counter-thesis review, and fail-closed validation.

It produces research artifacts for review. It does not place trades, provide personalized advice, or make trading recommendations.

Offline experiment and shadow-evaluation components live separately under
`backend/experiments/`. They use frozen, hashed datasets, causal features,
chronological out-of-sample splits, explicit transaction costs, and
hypothetical fills only; they never place orders or alter the research CLI.
Their command-line usage is documented in the package module help and covered
by the offline experiment tests.

## Architecture

```text
CLI / FastAPI
     |
  AgentLoop ──► model stream + skill selection + registered tools
     |                         |
     |              providers / financial agents / deterministic quant
     |
  ResearchEvent stream ──► TUI or HTTP SSE
     |
  SessionStore ──► transcript, checkpoints, trace, run artifacts
```

AgentLoop is the shared runtime used by both CLI and HTTP. Model streaming, tool execution, evidence accounting, and terminal-state decisions are separate runtime components. Provider snapshots are content-addressed under `.finai/provider-snapshots/`; the CLI can replay a complete archived model/data run without constructing live providers. The interactive UI is Textual + Rich over asyncio; one-shot/plain output remains available for automation. There is no Docker, PostgreSQL, vector database, embedding model, or local inference server. Phoenix tracing is optional and disabled by default.

## Setup

```bash
uv sync
cp .env.example .env
```

Set `HIVE_API_KEY` and `TINYFISH_API_KEY` in `.env`. The Hive adapter uses the OpenAI-compatible model endpoint and streams usage metadata when provided by the provider.

### Local Phoenix tracing

Install the optional tracing group and start Phoenix in a separate terminal:

```bash
UV_CACHE_DIR=.uv-cache uv sync --group observability
PHOENIX_WORKING_DIR=.finai/phoenix PHOENIX_DEFAULT_RETENTION_POLICY_DAYS=30 \
  uvx --from arize-phoenix==20.14.0 phoenix serve
```

Set `FINAI_OBSERVABILITY_ENABLED=true` in `.env`, run FIN-AI, then open
`http://127.0.0.1:6006`. Traces use the `fin-ai-local` project by default.
Set `FINAI_TRACE_CONTENT=metadata` to omit prompt and response content.
Phoenix is best effort: an unavailable collector never stops a research run.

## Run

```bash
PYTHONPATH=backend uv run python -m finai --help
uv run uvicorn app.main:app --reload
# Offline replay: the JSON file maps model_stream/fetch_* operations to hashes
PYTHONPATH=backend uv run python -m finai --replay-snapshots snapshots.json --plain "Analyze ABC"
```

The CLI runs read-only research tools without approval and asks for clarification only when the request needs user input. Requested structured reports are validated before display; if validation fails, FIN-AI explains the evidence gap instead of showing unsupported claims. The saved run artifact path appears with the completed response. Press `Esc` to cancel an active run safely; use `/debug` and `/logs` to inspect local artifacts. Context compaction is automatic at 90% of the configured 250K-token working budget.

## Verification

```bash
uv run ruff check backend evals
uv run python -m compileall -q backend evals
uv run python evals/run.py --help
uv run pytest backend/tests
```

Pytest is the regression suite, but live provider calls and the full suite are intentionally separate from the deterministic local benchmark.

## Evaluation evidence

Evaluation fixtures and runners are in [`evals/`](evals/). The current tracked
gold set is a synthetic contract fixture, not market evidence. The artifact-
derived status, baseline metrics, unavailable ablations, and unverified
latency measurements are recorded in the [technical evaluation report](docs/evaluation-report.md).
The offline runner and telemetry tools remain separate from live-provider
evaluation.

## Known limitations

- TinyFish and YFinance are live providers and can fail, rate-limit, or return incomplete data.
- Company-name resolution is not guessed; the user must confirm a ticker-shaped candidate.
- Qualitative evidence is limited to sources found and extracted during the current run.
- The benchmark currently needs permitted frozen source snapshots, source-use records, and human-authored risk/citation labels before quality claims are valid.
- No tracked latency or provider-usage artifact is available for a p50/p95 or cost result.
