# Benchmark report

## Current result

No benchmark is currently measured. `evals/gold/v1/tasks.jsonl` has zero cases and `evals/gold/v1/source-manifest.json` is an unpopulated manifest. The runner therefore returns `status: insufficient_evidence`.

Required next evidence:

- 100 labeled frozen cases across the five requested groups;
- matching recorded result JSONL;
- controlled Hive usage/latency records and pricing-version metadata;
- separate live runs on three days;
- ablations run against the same gold set.

Do not convert targets into achievements until those artifacts exist.
