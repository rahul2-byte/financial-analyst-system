# Judge-only evaluation

The supported semantic evaluator is the independently configured ChatGPT Codex
model (`gpt-6-luna`). It is not the agent provider and has no Hive fallback.
The evaluator receives the case, the saved run artifact, and deterministic
audit fields, then must return the strict schema in `evals/judge.py`.

## Commands

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

`preflight` exits non-zero when the local OAuth credential is missing. An
evaluation exits non-zero unless every case is measured and judged `pass`.
Unmeasured, malformed, insufficient-evidence, or failed judgments do not pass
the quality gate. The summary prints `quality_gate: passed`, `failed`, or
`incomplete`; only `passed` is eligible for final benchmark reporting. The old
human-label files remain backward-compatible historical artifacts and are not
used by this path.
