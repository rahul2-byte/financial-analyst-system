# Evaluation decisions

## 2026-09-12: Do not fabricate the gold benchmark

The repository does not contain frozen source snapshots or independent labels for the requested 100 cases. The evaluation scaffolding is present, but the gold JSONL remains empty and all benchmark output is explicitly marked insufficient. This preserves truthful evidence boundaries.

## 2026-09-12: Keep the evaluator independent of runtime orchestration

The runner consumes recorded JSON results instead of invoking agents or an LLM. This makes metric regressions reproducible and prevents live/provider drift from changing the offline benchmark.
