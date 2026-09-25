# Evaluation

## Evaluation taxonomy

The repository deliberately separates structural contract checks, replayable execution, live operational runs, semantic judging, and offline trading-style experiments. Their results must not be merged.

| Evaluation | Sources | What it measures | What it does not establish |
| --- | --- | --- | --- |
| Synthetic contract v1 | `evals/gold/v1/`, `.finai/evals/synthetic-v1-results.json` | Deterministic scoring and artifact contracts over 10 fixture cases | Market quality, provider correctness, model accuracy, or investment performance |
| Replay/offline runtime | `evals/offline.py`, local provider snapshots | Reproducible behavior and ablations under frozen evidence | Fresh provider quality or live latency |
| Live operational run | `evals/execute.py`, local `.finai/evals/` artifacts | Terminal outcomes, retries, timeouts, latency, and resource telemetry | Financial-answer accuracy, citation semantics, or returns |
| Live Upstox benchmark | `evals/upstox_benchmark.py` | Deterministic close/date/claim-binding checks over provider cases | Semantic correctness unless a judge is available |
| Semantic judge | `evals/judge.py` | Judge-labelled answer/support outcomes when artifacts and credentials are valid | Independent truth; judge failure becomes unavailable |
| Adversarial manifest | `evals/adversarial_v1.jsonl`, `evals/adversarial.py` | Manifest and assertion integrity for 40 safety cases | A completed live adversarial score was not found |
| Offline experiments | `backend/experiments/` | Temporal out-of-sample simulation with costs and hypothetical fills | Live trading performance or deployable strategy claims |

## Reproduce the synthetic contract result

```bash
PYTHONPATH=. UV_CACHE_DIR=.uv-cache uv run python -m evals.validate
PYTHONPATH=. UV_CACHE_DIR=.uv-cache uv run python evals/run.py \
  --mode offline \
  --tasks evals/gold/v1/tasks.jsonl \
  --results evals/gold/v1/baseline-results.jsonl \
  --manifest evals/gold/v1/source-manifest.json \
  --output .finai/evals/synthetic-v1-results.json \
  --expected-cases 10 \
  --model-id fixture-model \
  --prompt-version fixture-prompt \
  --configuration-hash fixture-config
```

The recorded synthetic artifact is classified `synthetic_contract` and uses a seeded fixture. Its values are:

| Metric | Result | Interpretation |
| --- | ---: | --- |
| Cases completed | 10/10 | Fixture execution completion |
| Abstention accuracy | 100% | 4 expected abstentions |
| Fail-closed rate | 40% | 4/10 fixture cases |
| Valid plan rate | 100% | Structural validity |
| Loop/error rate | 0% | Fixture loop errors |
| Major-claim support | 50% | Structural support metric |
| Numeric provenance | 50% | Structural provenance metric |
| Citation precision / recall | 70% / 70% | Fixture citation metric |
| Risk F1 | 100% | Fixture risk labels |

Retrieval metrics are zero/unavailable in this fixture because it has no real retrieval set. Human claim-support labels, judge agreement, provider recovery, cost, and market-data correctness are also unavailable.

## Recorded live operational evidence

The recorded 21 September 2026 run used Hive `zai-org/glm-5.3-flash`, three workers, and 150 attempted cases:

| Measure | Reported result |
| --- | ---: |
| Terminal success | 143/150 (95.3%) |
| Terminal partial | 5/150 |
| Terminal insufficient-data | 1/150 |
| Terminal failed | 1/150 |
| End-to-end latency | 45.7 s p50, 110.3 s p95 |
| Provider latency | 32.0 s p50, 79.4 s p95, n=146 |
| Retries | 22 |
| Timeout-affected streams | 6 |

These are reliability and latency measurements only. The local telemetry has a status-bucketing inconsistency: it records six partial outcomes where the report separates five partial and one insufficient-data outcome. The result should therefore be cited with the report’s classification and this limitation.

## Dataset and provenance limitations

The `real-v1` case manifest contains 150 cases derived from 26 private-evaluation-authorized Upstox snapshots. It is not 150 independent market observations. The recorded provenance inventory reports 119 total snapshots but only 26 valid snapshots, and the manifest has empty `gold_numbers` for the real-v1 result used by `evals/run.py`. Raw provider payloads and permissions remain local/private.

The repository contains no reproducible full semantic score for the 150-case set, no populated human claim-support label set, no validated provider-agreement result, no validated pricing manifest, and no investment-return result. The strongest judge artifact is a small eight-case pilot and is not a full benchmark.

## Metric definitions

`evals/metrics.py` implements task completion, abstention accuracy, major-claim support, unsupported-major-claim rate, numeric provenance, citation precision/recall, risk F1, valid-plan rate, fail-closed rate, loop/error rate, and retrieval hit rate/recall/MRR/nDCG. `evals/agreement.py` provides agreement and Cohen's kappa calculations, but no populated label result was found. `evals/reference_indicators.py` provides independent SMA, RSI, and MACD calculations, but no trustworthy production-agreement result was found.

## Semantic judge

The supported semantic evaluator is the independently configured ChatGPT Codex model (`gpt-6-luna`). It is separate from the agent provider and has no Hive fallback. Missing credentials, malformed output, incomplete cases, or failed judgments are unavailable rather than passing.

```bash
PYTHONPATH=backend:. UV_CACHE_DIR=.uv-cache \
  uv run python -m evals.judge preflight --model gpt-6-luna

PYTHONPATH=backend:. UV_CACHE_DIR=.uv-cache \
  uv run python -m evals.judge evaluate \
  --cases evals/gold/v1/tasks.jsonl \
  --artifacts-dir .finai/evals/artifacts \
  --output .finai/evals/judge-v1.jsonl \
  --model gpt-6-luna --prompt-version judge-v1
```

A run is eligible for benchmark reporting only when the summary reports `quality_gate: passed` for every case. This does not create independent ground truth.

## Offline experiment evaluation

`backend/experiments/cli.py` runs a separate deterministic pipeline:

```text
load dataset -> features -> signals -> temporal splits -> purge/embargo
-> next-bar execution -> costed simulation -> metrics -> registry artifact
```

The package does not ship a completed experiment result in the repository. It should not be described as a backtest result until a dataset, spec, artifact, and metrics output are supplied and reviewed.
