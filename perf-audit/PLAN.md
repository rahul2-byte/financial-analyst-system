# Performance plan

Sources: a1 (pipeline), a2 (data), a3 (frontend/bridge), a4 (measured: 149 real runs, glm-5.3-flash via Hive).

## What the measurements say
- End-to-end median 45.7 s, p90 91.7 s. LLM calls are ~99.6% of it.
- Final synthesis call: median 31.0 s (p90 71.5 s), ~1.5k output tokens. Tool-selection round: median 7.4 s.
- Tools: ~110 ms/run median in evals (likely snapshot/cached), except news ~13 s. Live provider latency (Upstox/yfinance/TinyFish) is not represented, so a2's network fixes still matter for live use.
- Nothing is shown to the user until the run finishes (no report streaming), so the UI shows a spinner for 30-90 s.

## Waves (each item = one Sonnet agent, worktree, disjoint files)

### Wave 1 — quick wins, no behaviour change
| ID | Work | Files owned | Expected gain |
|----|------|-------------|---------------|
| W1a | Lazy imports (quant/pandas_ta, report_view in bridge), trace/archive fsync only at run boundaries | backend/finai/bridge/*, backend/app/tools/tool_runner.py imports, backend/quant/__init__/fundamentals import sites, observability writers | -0.3-0.45 s startup/ready |
| W1b | Ink render perf: move ticker into LiveActivity, memo Composer/StatusLine/StreamingAnswer, fix seenSequences copy, minify bundle + compile cache | frontend/src/** , frontend build config | smooth UI, no 10-22 ms frames |
| W1c | Data quick wins: instrument search to_thread + short timeout, Upstox-first fundamentals, threaded Upstox bundle w/ shared client, OHLCV cache key normalisation, no timeout retry on Ticker.info, shared TinyFish httpx client | backend/data/**, backend/finai/session_runtime.py (search only) | live: seconds to tens of seconds on failures |

### Wave 2 — latency in the agent loop (runtime.py owner = one agent)
| W2a | Concurrent tool execution within a round (gather, results appended in call order) | backend/app/core/agent_loop/runtime.py | live news/data overlap (~13 s+ when news present) |
| W2b | Report fast-path: when ticker resolved, prefetch standard evidence concurrently and skip the tool-selection round; skip advisory checkpoint when evidence sufficient | runtime.py, routing_policy.py | ~7-10 s per report (median ~15-20%) |
| W2c | Progress events (stage, N/M tools, elapsed) + UI stage checklist | bridge event contract, frontend | perceived speed |

### Wave 3 — streaming the report (needs decision)
| W3 | Stream structured report sections / deterministic figures as soon as evidence exists; stream synthesis text per the review-gate decision | runtime.py, bridge, frontend render, docs/frontend.md | time-to-first-content from ~45 s to a few s |

### Also considered
- Output tokens drive the 31 s synthesis call: trimming report schema verbosity or a faster model for synthesis is the biggest raw lever but changes report content — user call.
- Prompt caching: provider-dependent (Hive/GLM); measure before doing.
