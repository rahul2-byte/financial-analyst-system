# FIN-AI Audit 04: Engineering Quality, DX, Docs, Evals, Product

## Summary
1. All local gates are green: ruff clean, mypy clean (205 files), 555 tests pass in 22s, evals.validate OK.
2. Reported 87.7% coverage is inflated because test files are counted in `--cov=backend`; production-only coverage is about 80.7% (7921 stmts, 1525 missed).
3. The eval harness is sound in design but has no populated semantic result: `gold_numbers` are empty in all 150 real-v1 cases, and 150 cases come from only 26 snapshots.
4. Distribution is the weakest area: `package = false`, no console script, no LICENSE/CHANGELOG/CONTRIBUTING/pre-commit/Docker, and TA-Lib native-build friction is undocumented.
5. Product is a solid research CLI for single-stock questions but lacks watchlists, portfolio, screener, alerts, comparison and export.

## Scores
- **Engineering quality: 8/10.** Strict-ish gates all pass, CI runs lint, types, eval integrity, adversarial manifest, smoke and coverage; tests are fast and offline. Deductions: coverage metric inflated, mypy skips untyped bodies, CI runs only Python 3.11 on a 3.11-3.14 claim, CI runs pytest twice, no pre-commit.
- **Product completeness: 4.5/10.** Strong grounding and fail-closed design, but narrow scope (no portfolio, watchlist, screener, peer comparison, alerts, export, charts), a model-provider stack that requires several private keys, and no install path beyond a source checkout.

## Gate results
| Command | Result | Key numbers |
|---|---|---|
| `uv run ruff check backend evals` | PASS | "All checks passed!" |
| `uv run mypy backend` | PASS | 0 errors, 205 source files; only `annotation-unchecked` notes (untyped bodies unchecked) |
| `uv run pytest backend/tests --cov=backend ... --cov-fail-under=70` | PASS | 555 passed, 0 failed, 2 warnings, 22.3s; total 87.70% (includes tests); production-only about 80.7% |
| `PYTHONPATH=. uv run python -m evals.validate` | PASS | "benchmark artifacts valid" |
| `PYTHONPATH=backend uv run python -m experiments --help` | PASS | help printed (note: `experiments/__main__.py` 0% covered) |

Ran with `uv run --offline`; nothing installed.

Lowest-coverage production modules (stmts / miss): `app/main.py` 0% (37/37), `experiments/__main__.py` 0% (2/2), `app/core/logging.py` 34% (154/102), `data/providers/yfinance.py` 39% (175/107), `finai/cli.py` 40% (103/62), `app/routes/health.py` 51% (47/23), `app/core/circuit_breaker.py` 54% (85/39), `finai/__main__.py` 55% (20/9), `app/observability/tracing.py` 61% (145/57), `finai/plain.py` 62% (39/15). Also `data/news_pipeline/extractor.py` 63% and `finai/session.py` 63%.

## Findings
| ID | Severity | Category | file:line | Evidence | Impact | Recommended fix | Effort |
|---|---|---|---|---|---|---|---|
| QP-01 | P1 | dx | pyproject.toml:`[tool.uv] package = false` | No `[project.scripts]`, no build system; README runs `PYTHONPATH=backend uv run python -m finai`. No `uv tool install`/pipx path. | A new user cannot install a `finai` command; must clone and set PYTHONPATH. Blocks any distribution. | Add build backend, package layout (or `packages`), `[project.scripts] finai = "finai.__main__:main"`; document `uv tool install .`. | M |
| QP-02 | P1 | docs | repo root | No LICENSE, CHANGELOG, CONTRIBUTING, SECURITY; `version = "0.1.0"` never bumped across 103 commits. | Legal ambiguity blocks reuse/contribution; no release history. | Add LICENSE, CHANGELOG (Keep a Changelog), CONTRIBUTING (can point to docs/development.md), tag releases. | S |
| QP-03 | P1 | eval | evals/gold/real-v1/cases.jsonl | 150 cases from 26 snapshots, `gold_numbers` empty in every case; docs/evaluation.md:68-70 admits no full semantic score, no populated human claim-support labels, only an 8-case judge pilot. | The harness cannot currently measure answer correctness or grounding; reported 95.3% is terminal success only (matches prior audit html). | Populate gold_numbers for price/fundamental cases from archived snapshots; hand-label 100+ claims; run judge on all 150 with kappa. | L |
| QP-04 | P2 | dx | pyproject.toml:12-27, README.md:46 | TA-Lib>=0.6.5 and vectorbt (pulls numba/llvmlite) are hard dependencies; no doc of native build requirements, no troubleshooting page. | Install can fail on platforms without a TA-Lib wheel; heavy install for a CLI. | Document wheel availability/fallback, add docs/troubleshooting.md; move vectorbt to an `experiments` dependency group. | M |
| QP-05 | P2 | dx | pyproject.toml `addopts`, CI ci.yml:48-52 | `--cov=backend` counts `backend/tests` itself: 87.7% reported vs about 80.7% production. CI also runs the full suite twice. | Misleading quality signal; wasted CI minutes. | Use `--cov=backend/app --cov=backend/finai ...` or omit `*/tests/*`; run pytest once with coverage. | S |
| QP-06 | P2 | dx | .github/workflows/ci.yml:18 | Only Python 3.11; pyproject declares `>=3.11,<3.14+`, mypy configured for 3.12, README claims 3.11-3.14. | 3.12-3.14 unsupported in practice unverified. | Add a matrix 3.11/3.12/3.13; align mypy python_version. | S |
| QP-07 | P2 | dx | pyproject.toml `[tool.ruff]`, `[tool.mypy]` | Ruff uses default rules only (E,F); no isort, bugbear, pyupgrade, no format check. Mypy not strict; untyped-def bodies unchecked (notes at observability.py:107,126 and test_news_pipeline_extractor.py:111). `[tool.mypy-evals.run]` is not a valid per-module table form (should be `[[tool.mypy.overrides]]`) so the override is likely ignored. | Weak lint; type errors hidden in unannotated functions. | Enable `select = ["E","F","I","B","UP","SIM"]`, `ruff format --check`, `check_untyped_defs = true`, fix the mypy override. | M |
| QP-08 | P2 | dx | repo root | No `.pre-commit-config.yaml`. | Lint/type failures found only in CI. | Add pre-commit with ruff, ruff-format, mypy. | S |
| QP-09 | P2 | docs | README.md / docs | No quick demo or sample output, no troubleshooting, no provider-key requirement matrix (Hive + OpenRouter + TinyFish needed for useful run); no mention of a keyless offline mode. | High onboarding friction; first run fails without three private providers. | Add "First run" with sample transcript, minimum viable key set, and troubleshooting. | M |
| QP-10 | P2 | docs | .github/workflows/ci.yml:62-67 | docs-sanity only greps for two stale script names; README references `.vscode/launch.json` which is gitignored (`.vscode/`). | Docs drift is not really checked. | Add markdown link checker and a command-list-vs-docs test (e.g. assert `/help` commands appear in docs). | S |
| QP-11 | P2 | dx | repo root | Untracked clutter: `.lavish/`, `.pi/`, `.playwright-mcp/`, `finai-evaluation-audit.html`, `audit/`; ignored but present `.opencode/`, `.uv-cache/`, `backend/.uv-cache/`. | Risk of accidental `git add .`; tool metadata may include session data. | Add `.lavish/ .pi/ .playwright-mcp/ .opencode/ .uv-cache/ audit/` to .gitignore or move the html under docs/. | S |
| QP-12 | P3 | dx | backend/mempalace.yaml (tracked) | Tracked tool-generated config for an unrelated memory tool, with auto-generated "rooms". | Repo noise; leaks personal tooling. | `git rm` and gitignore. | S |
| QP-13 | P3 | security | .gitignore | `.env` is ignored and `.env.example` exists (good; `.env` not opened). But `*.pem`, `*.key`, `.env.*` (other than the listed local ones) are not ignored; `backend/logs/research_sessions/*.jsonl` is covered only by the broad `logs/` rule. `.finai/` ignored (good). | Moderate chance of committing a `.env.prod` or key file. | Add `.env.*` with `!.env.example`, `*.pem`, `*.key`; add secret scanning (gitleaks) to CI. | S |
| QP-14 | P3 | dx | .github/workflows/ci.yml:21 | `pip install uv` (unpinned) instead of `astral-sh/setup-uv` with cache; no dependency caching, no pip-audit/dependabot. | Slow CI and unpinned tooling; no vulnerability scanning for a finance app. | Use setup-uv with cache, add Dependabot and `pip-audit`. | S |
| QP-15 | P3 | bug | backend/app/main.py, backend/finai/cli.py, backend/finai/__main__.py | 0%/40%/55% coverage on entry points; FastAPI app and CLI arg parsing barely exercised in tests (CLI smoke only `--help` in CI). | Regressions in startup/arg handling go unseen. | Add tests using `typer`/argparse invocation and TestClient for health. | S |
| QP-16 | P3 | dx | tests using network (test_news_pipeline_*, test_eval_upstox_benchmark) | Files mention network/socket terms; suite passes in 22s offline, so no live dependency observed, but there is no global socket-block fixture. | A future test can silently hit the network and become flaky. | Add `pytest-socket` / autouse fixture disabling sockets, `live` marker. | S |
| QP-17 | P3 | docs | finai-evaluation-audit.html | Prior audit headings: "95.3% terminal success is not accuracy", "Minimum work before claiming answer quality". docs/evaluation.md:68-70 still states the same gaps. | Issues are acknowledged in docs but not resolved (see QP-03). | Resolve QP-03 or move the audit into docs/ with status. | S |
| QP-18 | P3 | feature | Docker | No Dockerfile; README states this explicitly. | Reproducible deploy and TA-Lib build isolation unavailable. | Add a slim Dockerfile with TA-Lib build stage. | M |

## Feature roadmap to 10/10
1. Installable `finai` command (uv tool/pipx, release tags): without it nobody can try it.
2. Watchlists and portfolio/holdings import (broker CSV, Upstox): retail users think in portfolios, not single tickers.
3. Peer comparison and sector context: relative valuation is the core of equity research.
4. Screener (fundamental and technical filters, saved screens): discovery, not just lookup.
5. Alerts and scheduled briefs (price, earnings, filings, news): turns a tool into a habit.
6. Earnings/filings ingestion (BSE/NSE announcements, results PDFs, concall transcripts): primary-source grounding that NSE users need.
7. Export (PDF/Markdown/HTML report, CSV) and shareable research artifacts.
8. Charts in terminal/HTML (candles, indicator overlays, financial trends).
9. Corporate actions, shareholding pattern, promoter pledge, FII/DII flows, F&O/option-chain data: India-specific signals.
10. Backtest and paper-trade surface linking `experiments/` to the CLI with clear disclaimers.
11. Valuation models (DCF, multiples bands) as deterministic tools with editable assumptions.
12. Provider fallback and a keyless/offline demo mode with bundled fixtures.
13. Multi-provider LLM options (local/OpenAI/Anthropic) so users are not locked to Hive/OpenRouter.
14. Cost/latency display per answer and answer-quality scorecard in the UI.
15. Tax/charges-aware P&L and a research history search.

## Unverified
- Live provider behavior, LLM answer quality, and the 95.3% figure were not re-run (live/paid).
- Whether any test hits the network was inferred from keyword grep and the offline 22s pass, not from a socket-blocked run.
- Production-only coverage (80.7%) was computed from the term-missing table, not a clean rerun.
- TA-Lib install friction on other OSes and non-3.11 Python versions was not tested.
- Whether the `[tool.mypy-evals.run]` override is ignored was reasoned from mypy config syntax, not tested.
- `.env` contents and git history for secrets were not inspected (history not scanned).
- The "Textual UI", command set beyond `/commands.py` registry, and quant correctness were out of scope.
