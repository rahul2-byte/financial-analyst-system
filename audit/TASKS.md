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
