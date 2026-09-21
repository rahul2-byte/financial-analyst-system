# Local evaluation observations

## Archived session telemetry

Generated from `.finai/sessions/40c6bb19777d40bc8f362bed57e838b8/events.v1.jsonl`
on 2026-09-21 with `python -m evals.telemetry`.

| Metric | Value | Sample size |
|---|---:|---:|
| End-to-end p50 | 4,118.15 ms | 2 runs |
| End-to-end p95 | 316,859.65 ms | 2 runs |
| Provider p50 | 3,195.06 ms | 2 runs |
| Provider p95 | 89,813.58 ms | 2 runs |
| Completed | 1 | 2 runs |
| Completed with limited evidence | 1 | 2 runs |
| Timeouts | 0 | 2 runs |
| Verified prompt tokens | 3,726 total | 2 runs |
| Verified completion tokens | 2,443 total | 2 runs |

This is an archived two-run local observation, not a latency benchmark. It is
too small for stable tail latency claims, includes mixed terminal outcomes, and
does not include a pricing manifest, so cost is unavailable.

## Provider comparison status

The local archive contains repeated Upstox TCS.NS daily-price snapshots with a
latest recorded close of INR 2,105.00 on 2026-09-18. It does not contain an
independent provider snapshot for the same instrument, date, and adjustment
basis. Provider agreement is therefore `not measured`.

## Live adversarial status

One attempted live adversarial pass on 2026-09-21 reached the configured
ChatGPT Codex fallback and then failed because the Hive endpoint could not be
resolved (`Temporary failure in name resolution`). This is an external provider
connectivity failure, not an adversarial pass/fail score.
