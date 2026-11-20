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

The recorded 21 September 2026 run used a previous provider and model (recorded before the OpenRouter-only migration), three workers, and 150 attempted cases:

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

These are reliability and latency measurements only. The 95.3% is terminal success: the run reached a `success` terminal status. It does not measure whether any number in the answer is correct, whether citations support claims, or whether the answer matched the archived snapshot; a run can succeed and still state a wrong price. The local telemetry has a status-bucketing inconsistency: it records six partial outcomes where the report separates five partial and one insufficient-data outcome. The result should therefore be cited with the report’s classification and this limitation.

## Dataset and provenance limitations

The `real-v1` case manifest contains 150 cases derived from 26 private-evaluation-authorized Upstox snapshots. It is not 150 independent market observations. The recorded provenance inventory reports 119 total snapshots but only 26 valid snapshots, and, before the gold-number work below, every case had empty `gold_numbers`. Raw provider payloads and permissions remain local/private.

The repository contains no reproducible full semantic score for the 150-case set, no populated human claim-support label set, no validated provider-agreement result, no validated pricing manifest, and no investment-return result. The strongest judge artifact is a small eight-case pilot and is not a full benchmark.

## Gold numbers and numeric grounding

### How gold numbers are made

`gold_numbers` in `evals/gold/real-v1/cases.jsonl` are computed offline and deterministically from the stored provider snapshot of each case by `evals/reference_indicators.py` (no network, no model). The snapshot's content hash is verified before use. Each case also carries `gold_number_specs`, one entry per number with `value`, `tolerance_rel`, `tolerance_abs`, `snapshot_id`, `as_of` (the case `retrieved_at`), `last_bar`, `rows_used`, and `method`. `gold_numbers` stays a flat name-to-value map so existing readers (`evals/judge.py`, `evals/execute.py`) are unaffected.

- Only daily bars whose whole day has elapsed at the as-of time are used, so later rows cannot change a value (covered by a test).
- Numbers: last close/high/low/volume, previous close, 1-day change %, 52-week high/low, SMA/EMA(20), average volume(20), Wilder RSI(14), MACD(12,26,9). A number is omitted when the history is too short.
- Category mapping: `price`, `range`, `volume` and `grounding_check` cases (87 of 150) get numbers. The 63 `fundamentals`, `indicators` and `evidence_gap` cases expect an evidence-gap answer, so they stay empty (the Upstox validator also forbids gold numbers on evidence-gap cases). Fundamentals are not in the price snapshots and are not computed.
- Cross-check: RSI, SMA, EMA, MACD and signal agree with TA-Lib (the library behind `backend/quant/technical_engine.py`) to about 1e-12 on all 26 snapshots.
- 26 snapshots back the 150 cases, so these are not 87 independent observations.

```bash
# Needs the local, private .finai/provider-snapshots archive
PYTHONPATH=. uv run python -m evals.reference_indicators --archive .finai/provider-snapshots --write
PYTHONPATH=. uv run python -m evals.reference_indicators --archive .finai/provider-snapshots   # exit 1 if stale
```

The write is idempotent.

### Grounding score

`evals/grounding.py` extracts numeric claims from an answer and classifies each as matched (within tolerance of a gold or evidence value), contradicted (clearly labelled as a gold quantity such as "close" or "volume" but outside tolerance), or unverifiable (no label and no matching value). Dates, years, hashes and row/day counts are ignored. The claim score is matched claims divided by all numeric claims; the report also gives contradiction counts, gold coverage, and terminal success next to it. It makes no model calls and works offline on replay or live artifacts after the fact.

```bash
PYTHONPATH=. uv run python -m evals.grounding \
  --cases evals/gold/real-v1/cases.jsonl \
  --results .finai/evals/artifacts/real-v1-final \
  --output .finai/evals/grounding-real-v1-final.json
```

`evals/run.py` also adds a `grounding` section to its report whenever tasks have gold numbers and results carry a `report` or `answer` text; the synthetic v1 fixture has neither, so it reports zero cases scored.

Limits: labelling is keyword proximity, so a table that places several values near one label can produce false contradictions or false matches, and unlabelled numbers that happen to equal a gold value count as matched. Treat the score as a screening signal, not ground truth. On the recorded `real-v1-final` artifacts it flags many contradicted and unverifiable claims despite 143/150 terminal success, which supports the point that terminal success is not answer quality; the exact figures include heuristic noise and should be reviewed before being quoted.

LLM-judge semantic scoring is not done here. Grounding checks numbers only, not wording, reasoning, citation support, or abstention quality; the `evals/judge.py` results remain a separate, partial pilot.

## Metric definitions

`evals/metrics.py` implements task completion, abstention accuracy, major-claim support, unsupported-major-claim rate, numeric provenance, citation precision/recall, risk F1, valid-plan rate, fail-closed rate, loop/error rate, and retrieval hit rate/recall/MRR/nDCG. `evals/agreement.py` provides agreement and Cohen's kappa calculations, but no populated label result was found. `evals/reference_indicators.py` provides independent SMA, RSI, and MACD calculations, but no trustworthy production-agreement result was found.

## Semantic judge

The supported semantic evaluator is the independently configured OpenRouter model (`--model`, default `OPENROUTER_MODEL`). It uses no fallback models. A missing `OPENROUTER_API_KEY`, malformed output, incomplete cases, or failed judgments are unavailable rather than passing.

```bash
PYTHONPATH=backend:. UV_CACHE_DIR=.uv-cache \
  uv run python -m evals.judge preflight --model openai/gpt-5.6-luna

PYTHONPATH=backend:. UV_CACHE_DIR=.uv-cache \
  uv run python -m evals.judge evaluate \
  --cases evals/gold/v1/tasks.jsonl \
  --artifacts-dir .finai/evals/artifacts \
  --output .finai/evals/judge-v1.jsonl \
  --model openai/gpt-5.6-luna --prompt-version judge-v1
```

A run is eligible for benchmark reporting only when the summary reports `quality_gate: passed` for every case. This does not create independent ground truth.

## Offline experiment evaluation

`backend/experiments/cli.py` runs a separate deterministic pipeline:

```text
load dataset -> features -> signals -> temporal splits -> purge/embargo
-> next-bar execution -> costed simulation -> metrics -> registry artifact
```

The package does not ship a completed experiment result in the repository. It should not be described as a backtest result until a dataset, spec, artifact, and metrics output are supplied and reviewed.
