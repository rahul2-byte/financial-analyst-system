# Performance optimization — task tracker

| # | Task | Status | Agent | Output |
|---|------|--------|-------|--------|
| A1 | Audit report generation pipeline (AgentLoop, LLM calls, synthesis) | done | sonnet | perf-audit/a1-report-pipeline.md |
| A2 | Audit data layer + quant (yfinance/Upstox/TinyFish, caching, compute) | done | sonnet | perf-audit/a2-data-layer.md |
| A4 | Measure real stage timings from .finai ledgers | done | haiku | perf-audit/a4-measured-timings.md |
| A3 | Audit frontend Ink UI + JSON-RPC bridge (startup, render, streaming UX) | done | sonnet | perf-audit/a3-frontend-bridge.md |
| P1 | Synthesize prioritized plan | done | main | perf-audit/PLAN.md |
| W1a | Lazy imports + fsync at run boundaries | merged (uncommitted); --help 0.77s→0.12s; bridge import 0.61→0.24s | sonnet | perf/w1a |
| W1b | Ink render perf + bundle | merged (uncommitted); bundle 1.2MB→0.56MB; reducer 3000 ev 165→7ms | sonnet | perf/w1b |
| W1c | Data-layer quick wins | merged to checkout (uncommitted), 899 tests pass | sonnet (worktree) | perf/w1c |
| W2 | Agent-loop latency: concurrent tools + report fast-path (fixed evidence set, skip tool-selection round) + progress events | merged (uncommitted); 922 tests pass, evals.validate ok | sonnet | perf/w2 |
| W5 | LLM call-level study: reasoning tokens, review call, repairs, HTTP reuse, prompt size | done (NOTE: baseline was GLM/Hive; current default is claude-haiku-5.5 via OpenRouter) | sonnet | perf-audit/a5-llm-calls.md |
| W6a | Per-purpose reasoning control (tool/repair low, synthesis unchanged), HTTP keepalive/connect/pre-warm, persisted per-call telemetry + perf_report.py | merged (uncommitted); 934 tests pass |  sonnet | branch perf/w6a |
| W6b | Deterministic fail-closed pre-repair normaliser (citations, numeric links, JSON wrappers) + replay | merged (uncommitted); 953 tests pass; replay unmeasurable (trace schema drift) | sonnet | branch perf/w6b |
| X1 | News always prefetched for reports + required in synthesis; news pipeline internally parallel with waiting rate limiter; tool timeout aligned; fixed news truncation bug | merged (uncommitted); 964 tests | sonnet (perf-x1) | branch perf/x1 |
| X2 | Re-audit agent loop (merged code) for remaining delays | done | sonnet (read-only) | perf-audit/a6-agent-loop-recheck.md |
| X3 | Fast path every turn (unique ids, per-run dedupe); technical scan in prefetch + tools off for synthesis; skip checkpoint w/ facts; provider timeouts fit tool budget; per-run symbol-search cache; widen report detection; Event instead of poll for company name | merged (uncommitted); 996 tests | sonnet | branch perf/x3 |
| B1 | Live benchmark (paid) | declined by user — offline verification only | — | — |
| W4 | Bridge+UI render of progress events (stage checklist, N/M tools, elapsed, Esc hint) + initialize returns before FinAIRepl build (a3 d) | deprioritised (user: focus on LLM/API/agent loop) | — | — |
| W3 | Report streaming | dropped (user chose progress-only; content/model unchanged) | — | — |

Decisions (user, 2026-11-21): progress-only UI (no report streaming); fast path with fixed evidence set = yes; synthesis content/model unchanged.
Worktrees: .claude/worktrees/perf-w1{a,b,c} from feat/ts-frontend; run Python with `PYTHONPATH=backend uv run --no-sync`.
User focus (2026-11-21): LLM calls, API calls, agent loop parallelism; target ~50% report time cut. UI work (W4) deprioritised.
Decisions (user, 2026-11-21, later): no paid calls; synthesis reasoning stays untouched (FINAI_REASONING_SYNTHESIS unset).
W6a/W6b hit Sonnet usage limit mid-task (resets 6am IST); resume via SendMessage, partial work in worktrees.
User requirements (2026-11-21): all report data fetches parallel; news ALWAYS fetched and analysed for reports.
User decision: widen report detection (buy/sell/outlook/deep dive/analysis of single resolved stock) -> report flow.
