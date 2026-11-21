# A4: Measured wall-clock timings from real report runs

Source: local `.finai/` artifacts only (read-only, no network). Numbers only; no prompt, response, or report text.

## Headline table (primary set: `evals/real-v1-final-events.jsonl`)

149 completed runs (150 started; 1 ended in `run.failed`, excluded). Model: `zai-org/glm-5.3-flash` via provider `hive`, all 306 completed calls. Terminal status: 143 success, 5 partial, 1 insufficient_data.

| Metric | n | median | p90 | Notes |
|---|---|---|---|---|
| End-to-end run time | 149 | 45.7 s | 91.7 s | max 174.5 s. Cross-check: `real-v1-final-telemetry.json` p50 45.7 s, p95 110.3 s (p95 vs p90 differ by percentile choice) |
| LLM rounds per run (`model.request.started`) | 149 | 2 | 2 | histogram: 1 round: 2 runs; 2: 135; 3: 12; 4: 1 |
| Tool-using rounds per run | 149 | 1 | 1 | max 2 |
| Repair rounds per run | - | not recorded | - | no repair marker in events; see notes |
| LLM calls per run (completed) | 149 | 2 | 2 | 306 calls total; 334 attempts, so 28 extra attempts |
| Provider retries per run | 149 | 0 | 1 | `provider.retrying`, max 2 |
| Provider failures per run | 149 | 0 | 0 | max 2 |
| Each LLM call (`provider.completed.duration_ms`) | 306 | 17.2 s | 54.1 s | all calls pooled |
| Time to first token (per call) | 269 | 12.6 s | 34.2 s | `first_token_ms`, present on 269 of 306 calls |
| Tool-selection call (non-final round) | 157 | 7.4 s | 22.2 s | pooled non-final calls |
| Final report synthesis call (last call per run) | 149 | 31.0 s | 71.5 s | per run, last `provider.completed` |
| Final call prompt tokens | 149 | 3,726 | 6,086 | from `usage.prompt_tokens` |
| Final call completion tokens | 149 | 1,530 | 2,404 | from `usage.completion_tokens` |
| All-call prompt tokens | 306 | 1,150 | 6,009 | |
| All-call completion tokens | 306 | 692 | 2,079 | |
| LLM time per run (sum of call durations) | 149 | 43.7 s | 84.1 s | 99.6% of e2e at median |
| Tool time per run (sum of tool durations) | 149 | 110 ms | 1,164 ms | |
| Unaccounted time (e2e - LLM - tool) | 149 | 21 ms | 33 ms | orchestration overhead, negligible |
| run start to first tool start | 149 | 7.3 s | 22.0 s | first tool-selection round including provider wait |

### Tools (`tool.completed.duration_ms`)

| Tool (event name) | Purpose | Runs seen | n calls | median | p90 |
|---|---|---|---|---|---|
| `data:fetch_stock_data` | prices/OHLCV | 127 calls | 127 | 77.7 ms | 217 ms |
| `data:fetch_fundamentals` | fundamentals | 42 calls | 42 | 818 ms | 1,115 ms |
| `data:fetch_market_status` | market status | 5 calls | 5 | 95 ms | 154 ms |
| `news:fetch_news` | news (TinyFish pipeline) | 9 calls | 9 | 13.3 s | 17.2 s |
| `analysis:get_technical_overview` | technical | 76 calls | 76 | 10.2 ms | 13.7 ms |
| `analysis:run_technical_scan` | technical | 45 calls | 45 | 9.5 ms | 12.9 ms |
| `analysis:run_fundamental_scan` | fundamentals (quant) | 41 calls | 41 | 0.4 ms | 0.5 ms |
| search | not present in these events | - | - | - | - |

## Secondary set: `sessions/*/events.v1.jsonl` (mixed providers, not a single config)

102 session files, 127 runs started, 81 with `run.completed`. Terminal statuses across the 81: completed 30, success 16, completed_with_limited_evidence 11, awaiting_clarification 15, denied 4, partial 2, insufficient_data 3. Many runs also show `provider.failed` (82) and `run.failed` (33), so this set is mostly debugging or interactive activity.

| Metric | n | median | p90 |
|---|---|---|---|
| Routing (run start to `route.decision.made`) | 127 | 11 ms | 22 ms |
| Success+partial runs: end-to-end | 18 | 13.5 s | 77.6 s |
| Success+partial runs: LLM time | 18 | 11.9 s | 74.3 s |
| Success+partial runs: tool time | 18 | 0 ms | 2.2 s |
| Success+partial runs: LLM rounds | 18 | 2 | 4 |

Route decisions by `(execution_mode, model_tier)`: tool_only/none 35, model_answer/main 31, report_synthesis/main 30, deterministic/main 13, model_answer/small 12, deny/none 4.

Providers in these sessions: hive/GLM 34 calls, openrouter gpt 23, openrouter haiku 20, chatgpt_codex 14. Treat as indicative only (n=18 for success+partial).

## Files used and derivation

- `evals/real-v1-final-events.jsonl` (primary, 104,176 records, 150 runs): run durations from `run.started` and `run.completed.duration_ms`, cross-checked against the event gap; LLM call durations from `provider.completed.duration_ms` (plus `first_token_ms` and `usage`); tool durations from `tool.completed.duration_ms` (cross-checked against `tool.started` to `tool.completed` event gaps, which match within ms); rounds from `model.request.started` and `model.response.completed.has_tool_calls`. "Final synthesis" = the last `provider.completed` of each run, which is always the no-tool-call round in the rounds data.
- `evals/real-v1-final-telemetry.json`: cross-check only (p50 and p95 of end-to-end).
- `sessions/*/events.v1.jsonl`: secondary set; routing gap from `route.decision.made`, plus durations as above.
- `model-traces/2026-09-23/*.jsonl` (8 files, 29 calls, events `call.started`, `request.attempt`, `call.completed`): none of the 8 run_ids appear in the real-v1 set, and every request offered zero tools. Purpose cannot be assigned, so not used for timings.
- `evals/real-v1-results.json`, `evals/real-v1-final-results.jsonl`: not needed for timings.

Percentiles are nearest-rank on the per-run or per-call values (p90 = 90th percentile of the sorted list).

## Not recorded / caveats

- Route/Jev routing: no `route.decision.made` or stage events in the real-v1 set (150 runs have only the `agent` stage), so its time cannot be separated. Session runs show routing takes about 11 ms.
- Jev checkpoint: no marker in any file; cannot be measured.
- Repair rounds: no explicit marker. 13 runs had 3 or 4 model requests, but these could be extra tool rounds or repairs. Tool-using rounds never exceed 2, so the extra rounds are most likely repair or synthesis retries. Treat "repair rounds" as 0 to 2 extra rounds in 13 of 149 runs.
- Final synthesis call duration and tokens are measured; intermediate calls have tokens too, but per-call purpose is inferred from position (last call = synthesis, earlier calls = tool selection).
- Search tool: no search events in these runs.
- Cost: `pricing_version` is null, so no cost figures.
- Bottleneck: LLM generation dominates (~99.6% of e2e). The final synthesis call is the largest single item (median 31 s, roughly two-thirds of e2e). Tool time is small except `news:fetch_news` (about 13 s in 9 runs).
