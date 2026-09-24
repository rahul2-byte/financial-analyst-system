# Live GPT benchmark workflow

This workflow compares the FIN-AI report path using `gpt-5.6-luna` by default
and `gpt-6-luna` for explicit escalations. It does not change the application's
default Hive provider. Report quality and provider operations remain separate.

## Preconditions

- Configure `UPSTOX_ACCESS_TOKEN` and the ChatGPT Codex credential file locally.
- Use data only for an authorized local evaluation. These commands do not
  publish or redistribute source data.
- Choose a completed NSE trading date and record why it is appropriate.
- Keep generated manifests, provider snapshots, reports, and judge output under
  `.finai/`; they may contain licensed market data.

The collector freezes the selected instrument metadata and normalized candle
records returned by the existing Upstox adapter. That adapter does not retain
raw HTTP response bytes, so the archive is a normalized source record, not a
wire-response capture. Each case's numeric gold close is checked against its
content-addressed archived record before execution.

## 1. Pilot data and validation

Run a small, separate 8-key collection first:

```sh
PYTHONPATH=backend:. UV_CACHE_DIR=.uv-cache uv run python -m evals.upstox_benchmark \
  --trading-date 2026-09-22 \
  --count 8 \
  --output .finai/evals/upstox-pilot.jsonl \
  --confirm-local-evaluation-only

PYTHONPATH=backend:. UV_CACHE_DIR=.uv-cache uv run python -m evals.upstox_benchmark \
  --trading-date 2026-09-22 \
  --output .finai/evals/upstox-pilot.jsonl \
  --validate-only
```

The collector preserves the requested case count when a sampled key has no
candle for the selected date by recording an explicit `evidence_gap` case with
empty gold values. It does not silently reduce the sample. Inspect the
resulting manifest and source snapshots before moving on.

## 2. Pilot GPT run and judge

```sh
PYTHONPATH=backend:. UV_CACHE_DIR=.uv-cache uv run python -m evals.judge preflight \
  --model gpt-6-luna

FINAI_LIVE_EVAL=1 PYTHONPATH=backend:. UV_CACHE_DIR=.uv-cache uv run python -m evals.execute \
  --cases .finai/evals/upstox-pilot.jsonl \
  --expected-cases 8 \
  --output-dir .finai/evals/gpt-pilot-first/artifacts \
  --results .finai/evals/gpt-pilot-first/results.jsonl \
  --events .finai/evals/gpt-pilot-first/events.jsonl \
  --metrics .finai/evals/gpt-pilot-first/metrics.jsonl \
  --allow-live

PYTHONPATH=backend:. UV_CACHE_DIR=.uv-cache uv run python -m evals.judge evaluate \
  --cases .finai/evals/upstox-pilot.jsonl \
  --artifacts-dir .finai/evals/gpt-pilot-first/artifacts \
  --output .finai/evals/gpt-pilot-first/judge.jsonl \
  --model gpt-6-luna
```

Each completed case is durably written to its artifact before the JSONL result
and event snapshots are atomically refreshed. Resume verifies the manifest,
first-attempt results, models, attempt type, concurrency, and timeout against
`artifacts/run-state.json`, rebuilds those snapshots from completed artifacts,
and executes only cases without a completed artifact. If interrupted, repeat
the executor command with `--resume` added after `--allow-live`; keep the same
output paths and run options. `metrics.jsonl` is finalized when every case has
completed.

Inspect all 8 artifacts, event ledgers, deterministic answer-quality checks,
citations, model IDs, provider timings, and semantic judge results. The
executor's deterministic check requires an answer case to complete, pass
publication, and bind both the frozen close and matching timestamp in a major
claim. It separately checks expected evidence-gap abstention. This is not a
semantic score; the judge must report `quality_gate: passed` for every case
before starting the full run. The frozen benchmark tool result includes a
Python-computed `benchmark_context.date_matches` field so the model does not
have to infer the date comparison.

## 3. Full 150-key run

Repeat collection and validation with `--count 150` and a new output path. Then
repeat the pilot execution and judge commands using the full manifest, expected
case count `150`, and new `gpt-full-first` output paths. Keep first-attempt
results immutable.

## 4. Retry only eligible cases

After inspecting first-attempt results, use the same manifest and point
`--retry-of` at the first-attempt result file. The executor selects only
failed, partial, and limited-evidence cases, writes to new retry paths, and
reports the original denominator, retry-eligible count, recoveries, and cases
still unresolved.

The recorded benchmark GPT tool evidence is frozen per instrument/date, so GPT
answer-quality comparison does not drift with live market data. Stage timing
reports separate model provider durations and first-token latency from tool
duration. Upstox collection timing is a separate data-acquisition measure.
