# FIN-AI

FIN-AI is a CLI-first, human-in-the-loop financial research workflow for NSE/BSE equities. It combines deterministic Python quant analysis with Hive GLM-5.3-Flash, YFinance market data, TinyFish web search, source extraction, citation checks, counter-thesis review, and fail-closed validation.

It produces research artifacts for review. It does not place trades, provide personalized advice, predict returns, or claim investment performance.

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

AgentLoop is the production runtime used by both CLI and HTTP. Model streaming, tool execution, evidence accounting, and terminal-state decisions are separate runtime components. Provider snapshots are content-addressed under `.finai/provider-snapshots/`; the CLI can replay a complete archived model/data run without constructing live providers. The interactive UI is Textual + Rich over asyncio; one-shot/plain output remains available for automation. There is no Docker, PostgreSQL, vector database, embedding model, local inference server, or third-party telemetry SDK.

## Setup

```bash
uv sync
cp .env.example .env
```

Set `HIVE_API_KEY` and `TINYFISH_API_KEY` in `.env`. If the FastAPI HTTP surface is exposed, also set `HTTP_API_TOKEN` and optionally `HTTP_API_OWNER`; requests must send `Authorization: Bearer <HTTP_API_TOKEN>`. The Hive adapter uses the OpenAI-compatible chat-completions endpoint and streams usage metadata when provided by the provider.

## Run

```bash
PYTHONPATH=backend uv run python -m finai --help
uv run uvicorn app.main:app --reload
# Offline replay: the JSON file maps model_stream/fetch_* operations to hashes
PYTHONPATH=backend uv run python -m finai --replay-snapshots snapshots.json --plain "Analyze ABC"
```

The CLI pauses for clarification and plan approval when the request is incomplete, ambiguous, unsafe, or missing required evidence. Press `Esc` to cancel an active run safely; use `/debug` and `/logs` to inspect the latest state and local artifacts. Context compaction is automatic at 90% of the configured 250K-token working budget.

## Verification

```bash
uv run ruff check backend evals
uv run python -m compileall -q backend evals
uv run python evals/run.py --help
uv run pytest backend/tests
```

Pytest is the regression suite, but live provider calls and the full suite are intentionally separate from the deterministic local benchmark.

## Evaluation evidence

Evaluation design and artifacts are in [`docs/evaluation-design.md`](docs/evaluation-design.md), [`docs/benchmark-report.md`](docs/benchmark-report.md), and [`evals/`](evals/). Scores are only reported when generated from a versioned local gold set and recorded run metadata. No benchmark result is claimed in this README until it exists.

## Known limitations

- TinyFish and YFinance are live providers and can fail, rate-limit, or return incomplete data.
- Company-name resolution is not guessed; the user must confirm a ticker-shaped candidate.
- Qualitative evidence is limited to sources found and extracted during the current run.
- The benchmark currently needs populated frozen source snapshots and human-authored risk/citation labels before measured quality claims are valid.
