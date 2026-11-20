# FIN-AI product audit — task tracker

Audit only. No product code changes in this phase.

| # | Task | Agent | Status | Output |
|---|------|-------|--------|--------|
| 1 | UI/UX audit of CLI + Textual TUI (`backend/finai/`) | sonnet | done (spot-checked UX-01, UX-02, UX-04) | `audit/01-ui-ux.md` |
| 2 | Runtime/agent-loop/provider/security bugs (`backend/app/`) | sonnet | done (spot-checked RT-01) | `audit/02-runtime.md` |
| 3 | Data + quant correctness (`backend/data/`, `backend/quant/`, `backend/skills/`) | sonnet | done (spot-checked DQ-01) | `audit/03-data-quant.md` |
| 4 | Quality gates, tests, docs, evals, packaging, feature gaps | sonnet | done (spot-checked; QP-02 correction: LICENSE is tracked; only CHANGELOG/CONTRIBUTING missing) | `audit/04-quality-product.md` |
| 5 | Synthesis + prioritized roadmap | sonnet + main review | done | `audit/AUDIT.md` |

## Finding format (all reports)

`ID | Severity (P0 critical, P1 high, P2 medium, P3 low) | Category (bug, ux, feature, perf, security, dx, docs) | file:line | Evidence | Impact | Recommended fix | Effort (S/M/L)`

## Phase 0 — implementation (branch `phase0-fixes`)

| Agent | Findings | Owns | Status |
|---|---|---|---|
| UX (sonnet, worktree) | F-01, F-02, F-08, F-09, F-10 (cli), F-12, F-13, F-14, F-15 | `backend/finai/**` except session_runtime.py | merged (572 tests passed in worktree; diff reviewed) |
| Runtime (sonnet, worktree) | F-03, F-04, F-24, F-29, F-10 (tracing), F-30 | `backend/app/**` except ticker.py; `finai/session_runtime.py`; evals/upstox_benchmark.py | merged after 1 rework round (diff reviewed) |
| Data/quant/docs (sonnet, worktree) | F-07, F-18, F-22, F-43, F-46 | ticker.py, data, quant, experiments, CHANGELOG, CONTRIBUTING | merged (565 tests passed in worktree; diff reviewed) |

Merge: apply each worktree diff onto `phase0-fixes`, then run ruff + mypy + full pytest.

**Phase 0 result (combined branch):** ruff clean · mypy clean (208 files) · 609 tests passed · coverage 88.39% · evals.validate valid. Not yet committed.

## Phase 1 — "Trustworthy core"

### Wave 1 (parallel, worktrees)
| Agent | Findings | Owns | Status |
|---|---|---|---|
| P1-A1 tools/evidence | F-05, F-06, F-31, F-34, F-35, F-36, F-52 | agent_loop/tool_runner.py, tool_execution.py, evidence.py, finai/session_runtime.py | merged after 1 rework (F-05 non-claim exemptions) |
| P1-A2 services/safety | F-25, F-26, F-27, F-28, F-32, F-33, RT-20/21/26/28 | agent_loop/runtime.py, model_streaming.py, app/services/**, guardrails.py, security/** | merged after 1 rework (Codex params client-side; cancel path checked) |
| P1-B data/news | F-47 (adapter), F-48, F-49, F-50, F-51, F-53, F-54, F-55, F-56, F-57 | backend/data/**, quant/fundamentals.py, app/config/models.py | merged (DQ-22/25 skipped; ProviderUnavailable mapping follow-up to A1) |
| P1-C quant/experiments | F-19, F-37, F-38, F-39, F-40, F-42, F-44, F-45, F-47 (engine) | backend/quant/** except fundamentals.py, backend/experiments/** | merged (DQ-10 skipped) |

### Wave 2 (after wave 1 merges)
| Agent | Findings | Owns | Status |
|---|---|---|---|
| P1-D packaging/eng | F-21, F-71, F-72, F-73, F-76, QP-12..16 | pyproject.toml, .github/, .gitignore, README/docs install | merged after 1 rework (tracing test leak); uv.lock needs `uv lock` (network) |
| P1-E CLI/TUI streaming | F-11, F-16, F-17 | backend/finai/** except session_runtime.py | merged (733 passed) |
| P1-F evals | F-23 gold numbers + grounding score in CI | evals/** | merged (87/150 cases with gold numbers; grounding score offline) |

Deferred to wave 3 / Phase 3: F-20 (peer/benchmark analytics), F-41 (point-in-time universe).

**Wave 1 checkpoint (A1+A2+C):** ruff clean · mypy clean (211 files) · 685 passed. `ruff format --check` has 36 pre-existing unformatted files (handled by P1-D).

**Wave 1 complete (+B):** ruff clean · mypy clean (213 files) · 716 passed · evals.validate valid · experiments --help OK.

**Phase 1 complete:** ruff + format clean · mypy clean (217 files) · 750 passed · coverage 85.65% (production only) · evals.validate valid. Follow-up: ProviderUnavailable → non-retryable `provider_unavailable` tool failure.

## Phase 1.5 — hands-on usage test
| Agent | Scope | Status | Output |
|---|---|---|---|
| sonnet usage tester | 12 one-shot + 3 TUI live queries, numbers cross-checked vs yfinance | done | `audit/05-usage-test.md`, `audit/usage/runs/` |

**Usage test result (2026-11-20):** 3/10 in a degraded environment (ChatGPT quota exhausted → hive/glm fallback). 1/12 usable answers. Spot-checked: M&M rejected at guardrails.py:179; TCS direct route prints raw JSON. Root cause of "failed safety review": F-32 made reviewer *errors* return DENY (routing_policy.py:141-148).

## Phase 1.6 — usage fixes (parallel worktrees)
| Agent | Scope | Owns | Status |
|---|---|---|---|
| U1 sonnet | reviewer outage ≠ DENY, provider-fallback event fields, whole-run deadline, router reason, tracing banner | backend/app/** except guardrails.py, ticker.py, resolver | merged (diff reviewed) |
| U2 sonnet | M&M guardrail, INFY/ambiguity resolution, human direct-route answer, fallback + review notices, source labels, delisted message | backend/finai/**, guardrails.py, ticker.py, resolver | merged after 1 rework (fallback must not auto-resolve non-exact hits) |
| U3 sonnet | delisted/empty price message | tool_runner.py | merged |
| Re-test | rerun the 12 queries after merge (TUI needs tmux) | sonnet | done: 5/10 (was 3/10), 4/12 usable — `audit/06-usage-retest.md` |

**Phase 1.6 complete:** ruff + format clean · mypy clean (219 files) · 793 passed · coverage 85.89% · evals.validate valid · finai --help OK.

## Phase 1.7 — re-test fixes (parallel worktrees, base dcdfb6b)
| Agent | Scope | Owns | Status |
|---|---|---|---|
| R1 sonnet | deadline bounds model calls; sticky fallback; deterministic evidence summary when all LLMs fail | runtime.py, model_streaming.py, app/services/**, events/models.py, config/models.py, tests/test_runtime_budget.py | merged after 1 rework (summary only on provider outage; DENY stays fail-closed) |
| R2 sonnet | indicator key values survive truncation; Adani resolver ranking/stopwords; Tata message; dedupe sources | tool_runner.py, evidence.py, tool_execution.py, instrument_resolution.py, finai/**, tests/test_answer_quality.py | merged |
| Re-test 2 | rerun 12 queries | sonnet | queued |

**Phase 1.7 complete:** ruff + format clean · mypy clean (221 files) · 808 passed · coverage 86.04% · evals.validate valid.

## Phase 1.8 — OpenRouter-only + live fixes (parallel worktrees, base 72c43f0)
| Agent | Scope | Owns | Status |
|---|---|---|---|
| F1 sonnet | tool names `:`→`__` on the wire (fixes HTTP 400 on every tool call), readable HTTP errors, hermetic test key | openrouter_service.py, tests/conftest.py | merged after 1 rework (tests depended on developer `.env`) |
| F2 sonnet | human direct answers for technical/fundamental tools (no raw JSON) | finai/session_runtime.py | merged; follow-up: RELIANCE direct answer prints "close n/a" |
| F3 sonnet | 200 ms collector probe + ≤1 s tracing shutdown (was ~17 s exit) | observability/tracing.py | merged |
| Model compare | haiku-5.5 vs gpt-6.2-sol vs gpt-5.6-luna, 12 live runs | sonnet tester | done — `audit/09-model-compare.md`; sol only model with a synthesized compare report; haiku synthesis rejected → deterministic evidence dump |

**Phase 1.8 complete:** ruff + format clean · mypy clean (222 files) · 802 passed · coverage ~85.8% · evals.validate valid · finai --help OK.

## Phase 1.9 — staged answer checks with feedback retry; default gpt-6.2-sol
| Agent | Scope | Status |
|---|---|---|
| sonnet (worktree) | Report check → Fact check stages, stage-specific repair feedback, `check.stage` events + CLI lines, fallback names failed stage; default `openai/gpt-6.2-sol`, fallback `anthropic/claude-haiku-5.5` | merged; live test found regression (safety reviewer added to structured reports, rejected good report) |
| sonnet (main) | rework: reviewer only on pre-existing free-text path; unknown fact-ID hint | done |
| sonnet (worktree) | technical close read `Close` (yfinance); ROE %, D/E ratio display | merged |

Live (`audit/usage/stages/`): sol HDFC vs ICICI — report check failed (citation) → retried → published report, 61 s. Haiku still fails contract JSON / invents fact IDs → evidence fallback. RELIANCE direct answer shows close ₹1,377.50.

**Phase 1.9 complete:** ruff + format clean · mypy clean (223 files) · 812 passed · coverage ~86% · evals.validate valid.
