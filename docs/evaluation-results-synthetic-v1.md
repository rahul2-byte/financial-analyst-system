# FIN-AI evaluation result: synthetic contract v1

Generated on 2026-09-21 by:

```bash
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

## Classification

`synthetic_contract` — these are deterministic contract-fixture results, not
market-quality evidence and not a live model-performance benchmark. The source
manifest is explicitly marked `seeded_fixture`; no human claim-support labels
or independent source validation are included.

## Measured results

| Metric | Result | Denominator / note |
|---|---:|---|
| Cases completed | 10/10 | Recorded fixture cases |
| Task completion | 100% | 10 cases |
| Abstention accuracy | 100% | 4 expected abstentions |
| Fail-closed rate | 40% | 4/10 recorded `fail_closed` cases |
| Valid plan rate | 100% | 10/10 |
| Loop/error rate | 0% | 0/10 |
| Major-claim support rate | 50% | Structural case metric |
| Numeric provenance rate | 50% | Structural case metric |
| Citation precision | 70% | Structural case metric |
| Citation recall | 70% | Structural case metric |
| Risk F1 | 100% | Fixture risk labels |

## Unavailable metrics

The fixture has no real retrieval set, so retrieval scores are not evidence of
retrieval quality. Human semantic claim support, judge agreement, live latency,
token usage, cost, provider recovery, and market-data correctness are not
measured in this artifact.

## Resume usage

Do not use these numbers as financial-quality or production-performance claims.
They may be described only as a synthetic contract test, for example:

> Built a replayable evaluation contract covering 10 deterministic cases with
> 100% recorded task completion and explicit abstention/failure handling.

The raw machine-readable artifact is generated at
`.finai/evals/synthetic-v1-results.json` and is intentionally ignored by Git.
Regenerate it whenever the fixture, scorer, or code revision changes.
