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
