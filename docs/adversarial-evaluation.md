# Adversarial runtime evaluation

The 40-case manifest is `evals/adversarial_v1.jsonl`. It is validated without
network access:

```bash
PYTHONPATH=backend UV_CACHE_DIR=.uv-cache uv run python -m evals.adversarial
```

Live verification is deliberately explicit because it can call the configured
LLM and market providers:

```bash
FINAI_LIVE_EVAL=1 PYTHONPATH=backend UV_CACHE_DIR=.uv-cache \
  uv run python -m evals.adversarial --live --allow-live \
  --repeats 5 --output .finai/adversarial-v1.json
```

The runner records each transcript, terminal status, tool names, assertion
failures, timestamps, repeat count, and aggregate pass rate. It rejects tool
names outside the registered allowlist and detects multiple terminal events or
a successful terminal status after a failed tool. Semantic safety and source
support still require blinded human/LLM judging; the runner does not claim
that keyword checks prove semantic correctness.

The manifest's mocked tool payloads define hostile and degenerate scenarios for
an adapter-based harness. The current live runner uses real configured
providers; it does not silently substitute mocked data for live evidence.
