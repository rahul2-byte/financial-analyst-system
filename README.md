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

LLM-facing instructions are centralized and validated through the YAML-backed
`PromptRegistry`; see [`docs/prompt-management.md`](docs/prompt-management.md).

## Setup

```bash
uv sync
cp .env.example .env
```

Set `OPENROUTER_API_KEY`, `HIVE_API_KEY`, and `TINYFISH_API_KEY` in `.env`. OpenRouter Jev makes typed routing decisions; Hive GLM-5.3-Flash performs model generation by default. FIN-AI also contains an experimental, opt-in OpenCode-style ChatGPT OAuth provider. Enable it with `FINAI_CHATGPT_CODEX_ENABLED=true`, then run `python -m finai --chatgpt-login`; OAuth uses GPT-5.6 Luna by default, Terra for report repair, and Sol for final escalation. Hive remains the bounded fallback. The ChatGPT path uses an OpenCode-compatible internal Codex endpoint and may require changes if that endpoint or its access policy changes.

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

Evaluation fixtures and runners are in [`evals/`](evals/). The repository keeps
the synthetic contract fixture and a 150-case private-evaluation case manifest.
A live execution run on 21 September 2026 used `zai-org/glm-5.3-flash` through
Hive with three workers. It recorded 143 terminal `success` results (95.3%),
five `partial` results, one `insufficient_data` result, and one `failed` result.
End-to-end latency was 45.7 s p50 and 110.3 s p95 (150 runs); provider latency
was 32.0 s p50 and 79.4 s p95 (146 completed provider calls). The run observed
22 retries and six timeout-affected streams. These are execution-reliability
and latency measurements—not financial-answer accuracy, citation support, or
investment performance. The raw provider snapshots and run artifacts remain
local because their permitted use is private. Full conditions and limitations
are in the [technical evaluation report](docs/evaluation-report.md).

## Known limitations

- TinyFish and YFinance are live providers and can fail, rate-limit, or return incomplete data.
- Company-name resolution is not guessed; the user must confirm a ticker-shaped candidate.
- Qualitative evidence is limited to sources found and extracted during the current run.
- The 150 cases are derived from 26 private-evaluation-authorized Upstox snapshots; they are not 150 independent market observations, and raw provider payloads are not published.
- Execution success does not establish numeric grounding, semantic citation support, financial-answer accuracy, or investment performance. Independent judge scoring was unavailable for this run because the configured Codex account rejected the judge model identifier.
- Token-usage pricing was not returned for all calls, so no cost-per-report result is claimed.
