# Judge-only evaluation

The supported semantic evaluator is the independently configured ChatGPT Codex
model (`gpt-5.6-sol`). It is not the agent provider and has no Hive fallback.
The evaluator receives the case, the saved run artifact, and deterministic
audit fields, then must return the strict schema in `evals/judge.py`.

## Commands

```bash
PYTHONPATH=backend:. UV_CACHE_DIR=.uv-cache \
  uv run python -m evals.judge preflight --model gpt-5.6-sol

PYTHONPATH=backend:. UV_CACHE_DIR=.uv-cache \
  uv run python -m evals.judge evaluate \
  --cases evals/gold/v1/tasks.jsonl \
  --artifacts-dir .finai/evals/artifacts \
  --output .finai/evals/judge-v1.jsonl \
  --model gpt-5.6-sol --prompt-version judge-v1
```

`preflight` exits non-zero when the local OAuth credential is missing. An
evaluation exits non-zero if any case is unavailable or malformed. Those runs
must not be reported as accuracy. A complete run prints `status:
judge_evaluated`; only that status is eligible for a resume metric. The old
human-label files remain backward-compatible historical artifacts and are not
used by this path.
