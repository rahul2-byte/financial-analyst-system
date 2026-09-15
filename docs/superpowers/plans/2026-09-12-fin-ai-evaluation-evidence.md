# FIN-AI Evaluation Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, offline-first evaluation harness that computes the requested evidence metrics without fabricating gold labels or benchmark results.

**Architecture:** `evals/metrics.py` contains pure standard-library metric functions. `evals/run.py` loads versioned JSONL tasks and run-result JSONL, computes aggregate metrics, and writes a reproducibility record. Existing runtime output is consumed through a small JSON adapter rather than changed.

**Tech Stack:** Python 3.11+, standard library JSON/argparse/hashlib/statistics, pytest.

**Spec:** User-provided FIN-AI Evaluation, Metrics, and Evidence Plan.

## Global Constraints

- Offline deterministic evaluation uses versioned local snapshots and gold labels.
- Live operational evaluation is recorded separately and is never the primary benchmark.
- LLMs never perform quantitative calculations.
- No measured metric or cost is hard-coded into project claims.
- Missing gold labels or runtime evidence must be reported, not inferred.

### Task 1: Deterministic Metrics

**Files:**
- Create: `evals/metrics.py`
- Test: `backend/tests/unit/test_evaluation_metrics.py`

- [ ] Write failing tests for retrieval ranking, provenance, risk F1, policy gates, and aggregate percentages.
- [ ] Run the focused tests and confirm failure because the module is absent.
- [ ] Implement pure metric functions with zero-division-safe behavior and tolerance-aware numeric matching.
- [ ] Run the focused tests and the existing claim-verifier tests.

### Task 2: JSONL Runner and Artifacts

**Files:**
- Create: `evals/run.py`
- Create: `evals/gold/v1/tasks.jsonl`
- Create: `evals/gold/v1/source-manifest.json`
- Create: `evals/results/.gitkeep`
- Test: `backend/tests/unit/test_evaluation_runner.py`

- [ ] Write failing tests for JSONL loading, manifest hashing, empty/incomplete gold handling, and result output metadata.
- [ ] Run the focused tests and confirm failure.
- [ ] Implement the CLI with explicit `--mode offline|live`, `--tasks`, `--results`, `--manifest`, `--output`, and metadata fields.
- [ ] Keep the initial gold JSONL empty because no frozen source labels are present; emit `gold_cases=0` and `status=insufficient_evidence`.
- [ ] Run focused tests and the CLI against the empty scaffold.

### Task 3: Evaluation Documentation

**Files:**
- Modify: `README.md`
- Create: `docs/evaluation-design.md`
- Create: `docs/benchmark-report.md`
- Create: `docs/failure-taxonomy.md`
- Create: `docs/decisions.md`

- [ ] Document commands, metric definitions, offline/live separation, and current unmeasured state.
- [ ] State that Hive telemetry, 100 human-authored cases, and live 30-run data are pending actual collection.
- [ ] Run documentation/file validation and the backend test suite.

## Acceptance

- The runner never reports a benchmark pass with zero gold cases.
- Metric calculations are deterministic and tested.
- Results include commit, gold version, manifest hash, mode, timestamp, seed, and model/config fields when supplied.
- No README bullet contains invented performance, cost, scale, or expert-validation claims.
