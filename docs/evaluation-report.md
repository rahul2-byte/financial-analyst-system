# FIN-AI Technical Evaluation Report

## Scope

This report separates a synthetic contract fixture from a live execution
benchmark. Neither is a financial-performance benchmark or investment advice.

- `evals/gold/v1/` is a 10-case `synthetic_contract` fixture. It tests scoring
  and artifact contracts only.
- `evals/gold/real-v1/cases.jsonl` contains 150 live-execution cases generated
  from 26 private-evaluation-authorized Upstox snapshots. The cases reuse
  snapshots across query types and therefore are not 150 independent source
  observations.

The raw snapshots, execution artifacts, and telemetry are local `.finai/`
artifacts and are intentionally not committed: their authorization is limited
to the project owner's local evaluation use.

## Live execution run

Conditions: 21 September 2026, `zai-org/glm-5.3-flash` via Hive, three workers,
150 attempted cases. This was a live-agent reliability measurement; it did not
replay the archived provider response and it did not use a semantic judge.

| Measure | Result |
|---|---:|
| Terminal `success` | 143 / 150 (95.3%) |
| Terminal `partial` | 5 / 150 |
| Terminal `insufficient_data` | 1 / 150 |
| Terminal `failed` | 1 / 150 |
| End-to-end latency p50 / p95 | 45.7 s / 110.3 s (n=150) |
| Provider latency p50 / p95 | 32.0 s / 79.4 s (n=146) |
| Retries | 22 / 150 runs |
| Timeout-affected streams | 6 / 150 runs |

The timeout figure includes provider trajectories that ended partial; the
terminal-status table records the final outcome. One terminal failure was a
Hive transport timeout after a partial response. It was retained in the
baseline rather than retried into the score.

## Interpretation and limits

The measurements establish only the behavior of this live run under these
conditions. They do not measure financial-answer accuracy, numeric grounding,
semantic citation support, data-provider correctness, or investment outcomes.

An independent cross-family semantic judge was not available: the configured
ChatGPT Codex account rejected the requested judge model identifier. No
judge-derived claim-support score is reported. Provider token usage was absent
for some calls and no pricing manifest has been validated, so cost per report
is also not reported.

## Reproducing the structural checks

```sh
PYTHONPATH=backend:. UV_CACHE_DIR=.uv-cache uv run python -m evals.validate
PYTHONPATH=. UV_CACHE_DIR=.uv-cache uv run pytest backend/tests
```

Running the live workload additionally requires the project owner's provider
credentials, local snapshots, and explicit live-evaluation opt-in. The result
should be labelled with its run date, model, provider, and network conditions;
it must not be merged with the synthetic contract metrics.
