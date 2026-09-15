# Evaluation design

FIN-AI uses two isolated layers:

- Offline: versioned local source snapshots, JSONL gold labels, deterministic metric computation, and regression checks.
- Live: real provider/data calls recorded as operational diagnostics. Live results never replace the offline benchmark.

The runner computes source-discovery Recall@5/10, MRR@10, nDCG@10, evidence coverage, major-claim support, numeric provenance, citation precision/recall, risk F1, task completion, valid-plan rate, fail-closed rate, and loop/error rate. Missing evidence is zero-safe and reported as `insufficient_evidence`.

Each result records the git commit, gold-set version, source-manifest hash, prompt version, model ID, configuration hash, timestamp, mode, and optional random seed. Cost and latency are accepted as recorded runtime fields; they are not hard-coded.

The current v1 gold file is intentionally empty. It must be populated from permitted frozen sources with human-authored risk and citation labels before a benchmark claim is made.
