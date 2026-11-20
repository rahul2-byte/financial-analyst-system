# FIN-AI Master Audit

Combined from `01-ui-ux.md` (UX), `02-runtime.md` (RT), `03-data-quant.md` (DQ), `04-quality-product.md` (QP). Documentation only; no code changed. Master IDs are `F-xx`; every source ID is retained.

## 1. Executive summary
- FIN-AI is a well-gated CLI (ruff, mypy, 555 tests green) with a strong fail-closed publication design, but it is not yet trustworthy or complete enough to ship.
- The UI advertises features that do nothing: 7 of 16 slash commands, session picker/resume, `/mode`, fake "recent sessions", fake tools. This is a P0 trust problem.
- Grounding has reproduced bypasses: unit-suffixed numbers (`12bn`, `5x`) pass validation, multi-ticker fact IDs overwrite each other, and freeform answers have no grounding check.
- Data/quant has correctness holes: `M&M` and similar tickers are rejected, MACD is mislabelled, fundamentals units are ambiguous, and news dedupe merges "12%" with "21%".
- The eval harness cannot yet measure correctness (`gold_numbers` empty in all 150 cases), and there is no installable `finai` command.
- Recommended order: fix misleading behaviour and grounding first (about 1 week), then evals/reliability/packaging, then UX, then features.

## Scorecard
| Dimension | Score /10 | Weight |
|---|---|---|
| UX | 4.5 | 20% |
| Runtime reliability / security | 6.0 | 25% |
| Data / quant correctness | 5.5 | 25% |
| Engineering quality | 8.0 | 10% |
| Product completeness | 4.5 | 20% |
| **Weighted overall** | **5.5** (5.475) | 100% |

Weights are an editorial choice: correctness and reliability count most for a finance tool; UX and product completeness next; process quality least.

## Gate results
| Gate | Result |
|---|---|
| `ruff check backend evals` | clean |
| `mypy backend` | clean (205 files; untyped bodies unchecked) |
| `pytest backend/tests` | 555 passed, 22.3 s |
| Coverage | 87.7% total (includes test files); about 80.7% production-only |
| `evals.validate` | OK |

## 2. Master findings
Sev: P0 broken or misleading, P1 serious, P2 should fix. Effort: S under 1 day, M 1-3 days, L over 3 days. Findings confirmed against code by the reviewer: UX-01, UX-02, UX-04, DQ-01, RT-01.

### P0
| ID | Sev | Area | Title | Where (file:line) | Fix | Effort | Source IDs |
|---|---|---|---|---|---|---|---|
| F-01 | P0 | UX | 7 of 16 slash commands (`/sessions /resume /context /compact /history /retry`, plus unknown commands) only echo; no "unknown command" error | backend/finai/app_dispatch.py:64-105; commands.py:25-40 | Implement or remove each command; add "Unknown command, try /help"; wire `/retry`, `/history`, `/context`, `/compact` | M | UX-01 |
| F-02 | P0 | UX | Session picker unreachable; `session_callback` never invoked; Ctrl+K no-op | screens.py:79-127; app.py:165-166,285-286; cli.py:102-110 | Push `SessionScreen` on Ctrl+K and `/sessions`, call `session_callback`, rebuild view on resume, add `/resume <prefix>` | M | UX-02 |

### P1
| ID | Sev | Area | Title | Where (file:line) | Fix | Effort | Source IDs |
|---|---|---|---|---|---|---|---|
| F-03 | P1 | Runtime | `_NUMBER` regex misses unit-suffixed numbers (`12bn`, `5x`, `20bps`, `3Cr`, `12k`, `+5pp`), so unbound figures pass as verified | app/core/agent_loop/publication.py:~119, used ~277 and ~357 | Match digits plus trailing letters (`\d[\d,.]*\w*`); reject number-words; normalise first | S | RT-01 |
| F-04 | P1 | Runtime | Fact IDs omit the instrument; multi-ticker runs overwrite each other (RELIANCE 2500 replaced by TCS 4000) | app/core/agent_loop/evidence.py:~139, ~40 | Include instrument, period, interval in `fact_id`; reject collisions | S | RT-02 |
| F-05 | P1 | Runtime | Freeform answers have no grounding validation; model-memory numbers can be shown | finai/session_runtime.py:~244; agent_loop/runtime.py `_answer_contract` | Default to lookup/report contract when evidence tools exist, or add numeric binding to freeform | M | RT-03 |
| F-06 | P1 | Runtime | Blocking sync provider calls in the event loop, no per-tool timeout; cancel and `max_run_seconds` cannot fire | app/core/agent_loop/tool_runner.py:~274-420, 520-590, 770; tool_execution.py:19-60 | `asyncio.to_thread` plus `asyncio.timeout` per tool | M | RT-04 |
| F-07 | P1 | Data | Ticker regex lacks `&`: `M&M`, L&TFH, J&KBANK rejected (Nifty 50 name unusable) | backend/app/core/ticker.py:13 | Allow `&`; URL-encode in provider calls; test with `M&M.NS` | S | DQ-01 |
| F-08 | P1 | UX | `/mode` only echoes and accepts bogus values; `app.mode` never changes (false safety confirmation) | app_dispatch.py:100-103; app.py:279; cli.py:116 | Validate against 3 modes, set `self.mode`, refresh chrome, persist | S | UX-04 |
| F-09 | P1 | UX | `clear_pending_callback` bound to the old store after `/new` or resume; stale pending approval | cli.py:112; session.py:63-67 | Late-bound lambda or `repl.clear_pending()` | S | UX-03 |
| F-10 | P1 | UX | Phoenix tracing banner pollutes stdout and corrupts `--json`/`--plain` | cli.py:151-152; app/observability/tracing.py:112-137 | Suppress banner; tracing opt-in; diagnostics to stderr | S | UX-05 |
| F-11 | P1 | UX | One-shot buffers all output, no progress; failed run still exits 0 | cli.py:76-81,173-175 | Stream events (JSONL for `--json`); progress to stderr; exit codes 1/3/130 | M | UX-06 |
| F-12 | P1 | UX | Plain/one-shot shows `Sources · N` with no citation list; clarification is a dead end | plain.py:27-28,36-37 | Numbered source list with URLs; print clarification, distinct exit code, session id | S | UX-07 |
| F-13 | P1 | UX | Header broken at 80 columns (3 lines in 2-row widget, hardcoded space padding) | render.py:373-391; components.tcss:544 | Horizontal header with left/right segments; one-line narrow mode | S | UX-08 |
| F-14 | P1 | UX | Fake Attach/Web Search/Deep Research strip; `?` help promised but not bound | app.py:142-145,148; components.tcss | Delete fake strip; implement `?`/F1 help modal | S | UX-09 |
| F-15 | P1 | UX | Hardcoded fake "recent sessions"; Watchlist/Settings buttons dead; Reports dead-ends silently | widgets.py:485-500; components.tcss `#navigation`; app.py:168-171,281-309 | Remove mock data; populate from `SessionStore.list_sessions`; hide or implement buttons | M | UX-10 |
| F-16 | P1 | UX | Streaming re-parses whole markdown per delta (O(n^2)), fixed 10 ms sleep, forced auto-scroll | app.py:368-376,433-434 | Coalesce to about 10-15 Hz; scroll only when at bottom; drop sleep | M | UX-11 |
| F-17 | P1 | UX | Cancel plus queued query leaves a stuck "processing" widget; no "Cancelled" row | app.py:252-260,457-462 | Per-run state/widget; mount Cancelled row; start queue from message loop | M | UX-12 |
| F-18 | P1 | Quant | Simulator never trades at 100% target weight (cost exceeds cash, order skipped) | backend/experiments/simulation.py:399 | Size order as `cash/(price*(1+cost))`; emit rejection reason | S | DQ-02 |
| F-19 | P1 | Quant | Walk-forward splits are positional over a ticker-major frame; OOS windows not time-ordered | backend/experiments/cli.py:25-45; validation.py:122-133 | Split over sorted unique timestamps; assert monotonic time | M | DQ-03 |
| F-20 | P1 | Product | No peer/sector benchmark, relative strength vs NIFTY, beta/vol/drawdown/CAGR; valuation text always "no peer baseline" | backend/quant/, data/ (absent); quant/fundamentals.py:550-569 | Peer set (Upstox `competitors` is fetched and discarded), sector medians, price-statistics module | L | DQ-36, DQ-20 |
| F-21 | P1 | Eng | Not installable: `package = false`, no console script; needs `PYTHONPATH=backend` | pyproject.toml `[tool.uv] package = false` | Build backend, `[project.scripts] finai = "finai.__main__:main"`, document `uv tool install .` | M | QP-01 |
| F-22 | P1 | Docs | CHANGELOG and CONTRIBUTING missing; version 0.1.0 never bumped (MIT `LICENSE` is present and tracked) | repo root | Add CHANGELOG, CONTRIBUTING (and SECURITY); tag releases | S | QP-02 |
| F-23 | P1 | Eval | `gold_numbers` empty in all 150 cases (26 snapshots); no semantic or grounding score; 95.3% is terminal success only | evals/gold/real-v1/cases.jsonl; docs/evaluation.md:68-70 | Populate gold numbers from snapshots; hand-label 100+ claims; run judge on all 150 | L | QP-03, QP-17 |

### P2
| ID | Sev | Area | Title | Where (file:line) | Fix | Effort | Source IDs |
|---|---|---|---|---|---|---|---|
| F-24 | P2 | Runtime | Compaction and skipped tool calls orphan assistant `tool_calls` (provider 400) | runtime.py `_compact_model_history` ~1578; ~1152-1165, ~1130 | Drop assistant+tool pairs together; synthetic results for skipped calls | S | RT-05, RT-06 |
| F-25 | P2 | Runtime | Circuit breaker never opens on timeouts/connection errors; `_half_open_calls` never incremented | services/hive_service.py:~330-400 vs ~480-500; circuit_breaker.py:~84 | `record_failure()` in transport branch; increment half-open counter | S | RT-07 |
| F-26 | P2 | Runtime | Codex ignores max tokens, temperature, timeout; no whole-request deadline | services/chatgpt_codex_service.py:333-340, :377 | Send `max_output_tokens`/temperature; wrap in `asyncio.timeout` | S | RT-08 |
| F-27 | P2 | Runtime | Any transient refresh error deletes stored Codex credentials | chatgpt_codex_service.py:226-236 | Delete only on 400/401 `invalid_grant`; retry transient | S | RT-09 |
| F-28 | P2 | Security | Credential file written before chmod; default dir mode | chatgpt_codex_service.py:50-53 | `os.open(..., 0o600)`, dir 0o700 | S | RT-10 |
| F-29 | P2 | Security | Redaction is exact-key only (`access_token`, `x-api-key`, `HIVE_API_KEY` leak); two inconsistent redactors | app/security/policy.py:10, 25-45; tracing.py:14 | One regex-based redactor everywhere | S | RT-11 |
| F-30 | P2 | Runtime | Heuristic routing/ticker extraction: "price to earnings of TCS" returns raw price JSON; ticker becomes `TO` or `NSE` | services/routing_policy.py:~14,~150; session_runtime.py `_direct_tool_arguments` ~365 | Short imperative price pattern only; resolve via instrument resolver, drop token heuristic | S | RT-12, RT-14 |
| F-31 | P2 | Runtime | Direct-tool path skips `quality_status` and allowlist; degraded fundamentals reported "complete" | finai/session_runtime.py:~410-470; tool_runner.py:~850 | Reuse `valid_provenance`; report limited on degraded | S | RT-13 |
| F-32 | P2 | Security | Output safety review runs after text is streamed; router review is fail-open | runtime.py ~470-505; routing_policy.py:~118 | Buffer freeform until review, or document as advisory | M | RT-15 |
| F-33 | P2 | Security | Prompt injection: 3 English regexes; tool/news text and error strings reach prompts unsanitised; article text passed verbatim | app/core/guardrails.py:12-25; runtime.py ~1110, ~395, ~1060; news_pipeline/extractor.py:419-440; runner.py:195 | Delimit/quote tool content, sanitise reasons, never use system role for tool text; flag instruction-like text | M | RT-16, RT-17, DQ-31 |
| F-34 | P2 | Runtime | OHLCV/fundamentals caches never expire in long TUI sessions | tool_runner.py:~237-245, 461, 569 | Per-run cache or TTL | S | RT-18 |
| F-35 | P2 | Runtime | Unexpected tool exception (TypeError etc.) fails the whole run | agent_loop/tool_execution.py:36-52 | Catch `Exception` into a failure payload | S | RT-19 |
| F-36 | P2 | Runtime | yfinance fundamentals never become citable facts; reports hit `numeric_claim_unbound` fallback | tool_runner.py ~850; evidence.py:~118 | Promote/allow degraded with label | M | RT-23 |
| F-37 | P2 | Quant | Missing bar values a held position at zero (fake 40% drawdown) | backend/experiments/simulation.py:415-425 | Carry forward last mark; fail above gap tolerance | S | DQ-04 |
| F-38 | P2 | Quant | OOS windows stitched into one series; non-contiguous windows bridged | backend/experiments/cli.py:44-56 | Simulate each window separately and aggregate | M | DQ-05 |
| F-39 | P2 | Quant | Embargo and purge silently skipped when `label_horizon_bars=0` | experiments/cli.py:32-43; validation.py:136 | Reject embargo with horizon 0, or apply between train and test | S | DQ-06 |
| F-40 | P2 | Quant | `available_at` set to bar open-time, not close (latent leakage) | backend/experiments/features.py:23 | Use bar close time; assert `execution_time >= available_at` | S | DQ-07 |
| F-41 | P2 | Quant | Survivorship bias: static ticker list, no point-in-time universe or delisting | experiments/datasets.py; schemas.py:100-111 | Point-in-time constituent table; require universe snapshot hash | L | DQ-08 |
| F-42 | P2 | Quant | Volatility/Sharpe per-bar, not annualised; no CAGR, benchmark, INR risk-free | backend/experiments/metrics.py:68-93 | Annualised vol, CAGR, named fields | S | DQ-09 |
| F-43 | P2 | Quant | `MACD_12_26_9` value is the histogram; no signal/line/crossover | backend/quant/technical_engine.py:110-113 | Emit line, signal, histogram separately | S | DQ-11 |
| F-44 | P2 | Quant | `strength = min(abs(value)/100,1)` is meaningless; direction only for RSI | quant/technical_engine.py:29-48 | Remove or normalise per indicator; add directions | M | DQ-12 |
| F-45 | P2 | Quant | Registry lists 21 indicators, engine emits 17; metadata overstates coverage | quant/technical_registry.py:232-416; technical_engine.py:69-154 | Drive engine from `CORE_REGISTRY` or delete unused specs | M | DQ-13 |
| F-46 | P2 | Quant | One NaN or tiny OHLC violation aborts all technicals | quant/technical_engine.py:204-211 | Drop and count bad rows; hard fail above about 2% | S | DQ-14 |
| F-47 | P2 | Data | Naive timestamps depend on host timezone; `as_of` off by a day; partial intraday bar treated as closed | data/providers/yfinance.py:286-292; quant/technical_engine.py:63, 169-175 | `tz_localize` Asia/Kolkata; display IST; flag `partial_session` before 15:30 | S | DQ-15, DQ-16 |
| F-48 | P2 | Data | Missing OHLC defaulted to 0.0 (fabricated zero candles); `fetch_ohlcv` bypasses validator; adjustment implicit | data/providers/yfinance.py:199, 119-145, 214-227 | Reject rows; run quality validator; explicit adjustment | S | DQ-17 |
| F-49 | P2 | Data | Fundamentals lack provenance/units: `debtToEquity` percent printed as 45.3x, marketCap raw INR, `info` has no timeout | data/providers/yfinance.py:353-373; quant/fundamentals.py:504-505 | Normalise units at adapter; add `units`, `as_of`; timeout/retry; INR crore | M | DQ-19 |
| F-50 | P2 | Data | Macro indicators lack timestamp/currency; blanket except returns None | data/providers/yfinance.py:412-445 | Return `{value, as_of, currency, source}`; log failures | S | DQ-21 |
| F-51 | P2 | Data | No retry/backoff/429 handling/breaker in any adapter; Jev retry has no backoff; empty news key looks like "no news" | yfinance.py (all fetches); upstox.py:48-80; tinyfish_client.py:315-323; services/jev_service.py:~211 | Bounded retry with jitter; typed `ProviderUnavailable` reported as degraded | M | DQ-23, RT-25 |
| F-52 | P2 | Data | Upstox path ignores requested `period`, skips freshness/provenance; two technical tools can disagree | app/core/agent_loop/tool_runner.py:479-511 | Honour period; add freshness and provenance; single resolver; wire vendor cross-check | M | DQ-24 |
| F-53 | P2 | Data | Freshness is calendar-day (7 days) with no NSE calendar or gap/order checks; no session/valuation-band context | backend/data/quality.py:128-151; app/config/models.py:63 | Interval-aware thresholds; calendar from Upstox holidays; gap/order checks | M | DQ-26, DQ-38 |
| F-54 | P2 | Data | News dedupe merges different numbers/entities ("12%" vs "21%") | data/news_pipeline/normalize.py:111-116 | Numeric/entity guard plus shingled Jaccard | M | DQ-27 |
| F-55 | P2 | Data | Naive `publish_time` crashes scoring; future dates not penalised; recency never gates | data/news_pipeline/quality.py:205-210 | Normalise tz at ingest; penalise future dates | S | DQ-28 |
| F-56 | P2 | Data | Date parsing: epoch seconds read as ms; naive assumed UTC not IST; undated items bypass window | data/news_pipeline/connectors.py:39-66, 69-73 | Detect s vs ms; Asia/Kolkata default; flag undated | S | DQ-29 |
| F-57 | P2 | Data | Paywall detected but unused; stub marked `full` | news_pipeline/extractor.py:525-529; runner.py:186-222 | Downgrade to `partial`, cap quality | S | DQ-30 |
| F-58 | P2 | Product | Corporate actions, earnings calendar, shareholding, pledge, insider data fetched but not surfaced | backend/data/ (absent) | Normalised schemas with provenance; results-calendar tool | L | DQ-37 |
| F-59 | P2 | UX | Ctrl+C exits instantly; Ctrl+Z bound to exit; `copy_text` undefined; Shift+Enter unreliable | app.py:88-98,500-507; widgets.py:516-520 | Confirm exit; remove Ctrl+Z; Ctrl+J/Alt+Enter newline; real copy | S | UX-13 |
| F-60 | P2 | UX | No export/copy; Ctrl+E runs `/logs` printing placeholder path | app.py:92; app_dispatch.py:96-99 | `/export [md\|pdf\|html]`, `/copy`; real session dir | M | UX-14 |
| F-61 | P2 | UX | Activity hidden after completion; no stage timing; raw tool ids | app.py:361-434; render.py:325-370 | Collapsible activity summary with durations and labels | M | UX-15 |
| F-62 | P2 | UX | Clarification is plain text; reply starts a new run | app.py:410-416,274-277 | Selectable options modal; send chosen id | M | UX-16 |
| F-63 | P2 | UX | Sources panel: no full URL/publisher/date; duplicated in body; `[n]` not linked | render.py:438-457; app.py:417-423 | Navigable markers; `/sources open N`; `/copy N` | M | UX-17 |
| F-64 | P2 | UX | Approval shown twice; "yes" not echoed; Escape rejects | screens.py:182-193; app.py:261-273,476 | Echo decision; Escape defers; explain approval | S | UX-18 |
| F-65 | P2 | UX | Muted text about 3.9:1 contrast; no light theme; no NO_COLOR/ASCII mode | theme.py:384; components.tcss; finai (no NO_COLOR) | Raise muted to about `#8a8a8a`; high-contrast theme; honour NO_COLOR, `--ascii` | S | UX-19, UX-20 |
| F-66 | P2 | UX | 80x24 welcome is a wall of text; right rail (sources) hidden below 120 cols | app.py:49-75,136,179-192 | 3 clickable prompts; source count in status bar | M | UX-21 |
| F-67 | P2 | UX | Fallback REPL differs from TUI, prints unsanitised `event.text`, Ctrl+C unhandled | session.py:95-118,240-277 | Route through `render_event` and shared registry | M | UX-22 |
| F-68 | P2 | UX | Session list sorted by random id, reads all transcripts, IndexError on empty message | session_store.py:254-306 | Sort by last activity; index; guard empty | S | UX-23 |
| F-69 | P2 | UX | No `--version`/`doctor`; `--json` with no query opens REPL; bad `--session` silently creates one | cli.py:35-73,126-183 | `finai doctor`, `--version`, error on missing query, warn on unknown session | M | UX-24 |
| F-70 | P2 | UX | Raw failure text with no remediation | supervisor.py:26-31; render.py:533-546 | Map failure categories to remediation and `/retry` hint | S | UX-25 |
| F-71 | P2 | Eng | TA-Lib/vectorbt hard deps; native build undocumented | pyproject.toml:12-27; README.md:46 | Document wheels; troubleshooting page; vectorbt into an optional group | M | QP-04 |
| F-72 | P2 | Eng | Coverage inflated by counting tests; CI runs suite twice; CI only on 3.11 | pyproject.toml addopts; ci.yml:48-52, :18 | Production-only `--cov`; run once; 3.11-3.13 matrix; align mypy version | S | QP-05, QP-06 |
| F-73 | P2 | Eng | Ruff default rules only; mypy not strict; override table likely ignored; no pre-commit | pyproject.toml `[tool.ruff]`, `[tool.mypy]` | Add rules I,B,UP,SIM, `ruff format --check`, `check_untyped_defs`, fix overrides; pre-commit | M | QP-07, QP-08 |
| F-74 | P2 | Docs | No first-run demo, key matrix, troubleshooting, offline mode | README.md / docs | "First run" with sample transcript and minimum key set | M | QP-09 |
| F-75 | P2 | Docs | docs-sanity weak; README cites gitignored `.vscode/launch.json` | ci.yml:62-67 | Link checker; assert `/help` commands appear in docs | S | QP-10 |
| F-76 | P2 | Eng | Untracked tool clutter risks accidental commit | repo root (`.lavish/ .pi/ .playwright-mcp/ audit/`, html) | Add to .gitignore or move html under docs/ | S | QP-11 |

### P3 (grouped)
- Runtime: cancellation swallowed (RT-20, runtime.py ~340/~1085); shared `last_report_result` (RT-21); percent/fraction formatting (RT-22, publication.py ~560); fabricated `observed_at` (RT-24, tool_runner.py:~940); OAuth stray-request abort (RT-26, chatgpt_codex_service.py:~168-195); docs overstate breaker/budgets/redaction (RT-27, docs/architecture.md:141,160); 1024-token round-1 cap (RT-28, model_streaming.py:~62-75).
- Quant/data: sector limit unenforced, optimistic costs, churn (DQ-10, simulation.py:378-380); adjustment provenance mismatch (DQ-18, yfinance.py:301-328); news junk dates/content (DQ-22, yfinance.py:478-503); Upstox date/BSE/exact-symbol (DQ-25, upstox.py:254, 260); `_run_sync` thread leak (DQ-32, runner.py:41-52); URL normaliser/relevance/tiering (DQ-33); empty skill dirs (DQ-34, backend/skills/*); yfinance perf (DQ-35); missing S/R, 52-week, relative volume, crossovers (DQ-39).
- UX: tick re-renders chrome (UX-26); no history/Ctrl+R, palette, watchlist, charts (UX-27); no Pilot/snapshot tests (UX-28, app.py 512 lines); "Contacting Hive" jargon (UX-29, state.py:76-83,129); shortcuts undiscoverable (UX-30, app.py:148).
- Eng: tracked `backend/mempalace.yaml` (QP-12); `.gitignore` gaps `.env.*`, `*.pem` (QP-13); `pip install uv` unpinned, no pip-audit (QP-14, ci.yml:21); entry-point coverage 0-55% (QP-15); no socket-block fixture (QP-16); no Dockerfile (QP-18).

## 3. Roadmap
### Phase 0 "Stop the bleeding" (about 1 week; mostly S items, about 6-8 dev-days)
IDs: F-01, F-02 (minimum: remove or implement), F-03, F-04, F-07, F-08, F-09, F-10, F-12, F-13, F-14, F-15, F-18, F-22, F-24, F-29, F-30, F-43, F-46.
Exit criteria: no advertised command or button is a silent no-op; `/mode` changes mode; `--json` stdout is valid JSON; the `12bn` and two-ticker regressions fail before and pass after; `M&M.NS` resolves; header readable at 80x24.

### Phase 1 "Trustworthy core" (about 3-4 weeks)
IDs: F-05, F-06, F-11, F-16, F-17, F-19, F-20 (start), F-21, F-23, F-25-F-28, F-31-F-36, F-37-F-42, F-44, F-45, F-47-F-57, F-71-F-73, F-76, plus RT/DQ P3 items.
Exit criteria: gold numbers populated and grounding score reported in CI; every tool call has a timeout and runs off the event loop; breaker opens on transport errors; one-shot exit codes defined; `uv tool install .` yields a `finai` command; production-only coverage gated.

### Phase 2 "Delightful UX" (about 3 weeks)
IDs: F-58 (calendar/corporate actions surfaced), F-59-F-70, F-74, F-75, UX-26..UX-30 (command palette, history/Ctrl+R, help, sessions, exports, charts and sparklines, Pilot tests).
Exit criteria: sessions list/resume/export work; `?` help and a Ctrl+P palette exist; 80x24 and NO_COLOR pass Pilot snapshots; first-run guide and `finai doctor` ship.

### Phase 3 "10/10 features" (quarter-scale, ranked from DQ and QP feature lists)
1. Peer comparison and sector context with valuation bands (F-20, DQ-36/38). 2. Watchlists and portfolio import (QP list). 3. Corporate actions, shareholding, pledge, FII/DII, earnings calendar (F-58). 4. Export of PDF/MD/HTML research artifacts (F-60). 5. Charts (terminal/HTML). 6. Screener. 7. Alerts and scheduled briefs. 8. Filings/concall ingestion. 9. Point-in-time universe backtests surfaced in CLI (F-41). 10. DCF/multiples tools. 11. Keyless demo mode and multi-provider LLM choice. 12. Cost/latency display and Dockerfile (QP-18).
Exit criteria: each feature ships with deterministic Python calculations, provenance, and gold-number evals.

## 4. Suggested first PRs
1. **Allow `&` in tickers** (F-07). Files: backend/app/core/ticker.py, provider URL encoding. Test: `parse_ticker("M&M.NS")` and `"L&TFH"` pass; yfinance request mock receives the encoded symbol.
2. **Bind unit-suffixed numbers in publication validator** (F-03). Files: app/core/agent_loop/publication.py. Test: parametrised `12bn`, `5x`, `20bps`, `3Cr`, `12k` with no matching fact must fail validation.
3. **Instrument-scoped fact IDs** (F-04). Files: app/core/agent_loop/evidence.py. Test: two `fetch_stock_data` results (RELIANCE.NS, TCS.NS) yield two distinct facts with their own values.
4. **Real `/mode` and unknown-command handling** (F-08, F-01 part). Files: finai/app_dispatch.py, app.py. Test: Pilot sends `/mode review` and asserts `app.mode == "review"`; `/mode bogus` and `/bogus` show an error.
5. **Clean stdout for `--json`/`--plain`** (F-10). Files: finai/cli.py, app/observability/tracing.py. Test: subprocess with tracing enabled; `json.loads(stdout)` succeeds and banner text is absent.
6. **Late-bound `clear_pending` after `/new`** (F-09). Files: finai/cli.py, session.py. Test: create session, `/new`, reject approval, assert the new store's pending file is cleared.
7. **Fix MACD output** (F-43). Files: quant/technical_engine.py. Test: fixture series gives separate MACD line `-2.0068`, signal, histogram `0.0264`.
8. **One-shot exit codes and failure detection** (F-11 part). Files: finai/cli.py. Test: a stubbed failed run makes `run_one_shot` return non-zero.

## 5. Unverified across audits
- No live provider or LLM run in any audit; yfinance (`dividendYield`/`debtToEquity` units, `auto_adjust`), Upstox, TinyFish and Codex behaviour were inferred from code (RT-07 and RT-08 from control-flow reading, DQ-17, DQ-19, DQ-24 suspected).
- UX-12 root cause (queued start in cancelled task vs shared state) not isolated; approval modal, `SessionScreen` and Reports visuals read from code only; UX-19 contrast computed by hand; UX-13 Textual `copy_text` and Shift+Enter not tested.
- Whether the Phoenix banner (F-10) appears depends on `FINAI_OBSERVABILITY_ENABLED`, not read from `.env`.
- RT-15, RT-17, RT-18, RT-22, RT-23 are suspected, not reproduced; several RT line numbers are approximate (`~`).
- Not reviewed in depth: events/ledger.py, core/quota.py, core/resources.py, routes/health.py, core/logging.py.
- Coverage 80.7% production-only was derived from the term-missing table; sockets-in-tests, TA-Lib install on other OSes/Pythons, mypy override being ignored, and git history for secrets were not verified.
- KC_20/CMF_20 (pandas-ta-classic) numerical correctness and DQ-03 impact on fitted strategies are unchecked.
- QP-02 resolved: `LICENSE` (MIT) has been tracked since the initial commit `6b3de13`; only CHANGELOG/CONTRIBUTING are missing.
