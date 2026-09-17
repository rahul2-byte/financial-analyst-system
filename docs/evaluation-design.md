# Evaluation design

FIN-AI uses two isolated layers:

- Offline: versioned local source snapshots, JSONL gold labels, deterministic metric computation, and regression checks. Each permitted public snapshot must record its retrieval timestamp and SHA-256 hash; the seeded v1 fixture is only a contract fixture.
- Live: real provider/data calls recorded as operational diagnostics. Live results never replace the offline benchmark.

The runner computes source-discovery Recall@5/10, MRR@10, nDCG@10, evidence coverage, major-claim support, numeric provenance, citation precision/recall, risk F1, task completion, valid-plan rate, fail-closed rate, and loop/error rate. Missing evidence is zero-safe and reported as `insufficient_evidence`.

Each result records the git commit, gold-set version, source-manifest hash, prompt version, model ID, configuration hash, timestamp, mode, and optional random seed. Cost and latency are accepted as recorded runtime fields; they are not hard-coded.

Citation and claim correctness labels require two independent human labelers and adjudication records for disagreements. Live operational rates are computed separately by `evals.live_metrics.aggregate_live_runs` and never replace offline scores.
