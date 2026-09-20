# Bounded Offline Runtime Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a replay-only offline command that runs the existing FIN-AI `AgentLoop` once per approved case and writes one immutable, reproducibility-complete result artifact per case.

**Architecture:** Add a dedicated `evals/offline.py` command rather than extending the existing scoring-only `evals/run.py` live/offline switch. The command will use `ProviderArchive`, `build_runtime_resources(replay_snapshots=...)`, `FinancialToolRunner`, and `AgentLoop`; it will never construct live providers. It will collect typed runtime events into a case result, write the result atomically without overwriting, and return a nonzero exit code when any case fails or cannot run.

**Tech Stack:** Python 3.11+, asyncio, argparse, JSON, Pydantic runtime models, existing `AgentLoop` and provider replay components, pytest.

**Spec:** Approved in-chat bounded design from 2026-09-19.

## Global Constraints

- The command is offline-only; live-provider evaluation remains outside this command and outside its artifacts.
- Every case must be approved and must include a replay `model_stream` hash; missing replay inputs produce an explicit failed case artifact and a nonzero command result.
- Existing replay behavior remains authoritative: no live-provider fallback and no successful fixture substitution.
- Exactly one immutable `<output-dir>/<case-id>.json` artifact is written per valid case; existing artifacts are never overwritten.
- Artifacts record code revision and dirty state, model ID, declared prompt/skill versions, observed skill versions, replay/source hashes, configuration, UTC timestamps, report text, terminal status, and failure details.
- Synthetic replay fixtures in tests are runtime-contract fixtures only, never financial-quality evidence.
- No model download, CUDA installation, provider call, paid API, licensed data, or human labeling is required.

## Review Focus

- A missing `model_stream` replay hash must fail the case rather than instantiate live providers; covered by `test_offline_case_requires_model_replay`.
- A replay/provider archive failure must produce a failed artifact with failure details; covered by `test_offline_case_writes_failure_artifact`.
- A successful replay must capture report text and terminal status from runtime events; covered by `test_offline_case_writes_report_and_terminal_status`.
- A second attempt must not overwrite an existing artifact; covered by `test_result_artifact_is_immutable`.
- A missing or duplicate case ID must not be silently skipped; covered by `test_offline_case_manifest_rejects_missing_or_duplicate_ids`.

## Case manifest contract

The command will consume JSONL records with this shape:

```json
{
  "id": "case-001",
  "approved": true,
  "query": "Analyze the approved replay input.",
  "model_id": "replay-model",
  "prompt_version": "prompt-v1",
  "declared_skill_versions": {"report-synthesis": "1.0.0"},
  "source_hashes": ["<approved-source-hash>"],
  "replay_snapshots": {
    "model_stream": "<64-hex-hash>",
    "fetch_stock_price": "<64-hex-hash>",
    "fetch_fundamentals": "<64-hex-hash>",
    "fetch_news": "<64-hex-hash>"
  },
  "configuration": {"mode": "guided", "publish_reports": true}
}
```

`replay_snapshots` may contain only the existing operation keys accepted by `build_runtime_resources`; the model stream is mandatory. Source hashes are copied into the result metadata and are not interpreted as semantic support.

## Result artifact contract

Each case artifact will contain:

```json
{
  "artifact_version": "v1",
  "case_id": "case-001",
  "mode": "offline_replay",
  "run_id": "<uuid>",
  "query": "...",
  "report": "...",
  "terminal_status": "success",
  "failure_details": [],
  "metadata": {
    "code_revision": "<git sha or null>",
    "working_tree_dirty": false,
    "model_id": "replay-model",
    "prompt_version": "prompt-v1",
    "declared_skill_versions": {},
    "observed_skill_versions": {},
    "source_hashes": [],
    "replay_snapshots": {},
    "configuration": {},
    "started_at": "<UTC ISO timestamp>",
    "completed_at": "<UTC ISO timestamp>"
  }
}
```

Failure artifacts use `terminal_status: "failed"`, preserve any partial report text, and put exception/event details in `failure_details`. They are still artifacts and still make the command fail.

### Task 1: Add failing tests for the offline command

**Files:**
- Create: `backend/tests/unit/test_offline_evaluation.py`
- Read: `backend/app/core/agent_loop/replay.py`, `backend/app/core/resources.py`, `backend/app/core/agent_loop/runtime.py`, `backend/app/observability/provider_archive.py`

**Interfaces:**
- Consumes the planned `evals.offline` functions `run_offline_case`, `run_offline_cases`, and `write_result_artifact`.
- Produces tests that pin replay-only construction, event capture, failure artifacts, manifest validation, and immutable writes.

- [ ] **Step 1: Write a local replay fixture helper in the test file**

Use `ProviderArchive(tmp_path)` and `ProviderSnapshot` with a model-stream payload such as one token event. This fixture is only for runtime behavior and must not contain financial claims.

- [ ] **Step 2: Add the success artifact test**

Run one approved case through `run_offline_case`, then assert the artifact contains the case ID, replay mode, captured token/report text, a nonempty terminal status, model ID, prompt version, replay hash, and timestamps.

- [ ] **Step 3: Add the missing-model-replay test**

Call `run_offline_case` with no `model_stream` hash and assert it returns/records a failed case rather than constructing a live provider.

- [ ] **Step 4: Add the replay-failure artifact test**

Provide a nonexistent model-stream hash and assert the result artifact exists, has `terminal_status: "failed"`, and contains the archive failure message.

- [ ] **Step 5: Add the immutable-write test**

Write an artifact once, call `write_result_artifact` again for the same path, and assert it raises `FileExistsError` while the original bytes remain unchanged.

- [ ] **Step 6: Add manifest completeness tests**

Pass cases with a missing ID and duplicate IDs to `run_offline_cases` or its validator and assert explicit errors/nonzero behavior rather than skipped output.

- [ ] **Step 7: Run the focused tests to verify RED**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest backend/tests/unit/test_offline_evaluation.py -q -o addopts=''
```

Expected: collection fails because `evals.offline` does not yet exist.

### Task 2: Implement replay-only execution and immutable artifacts

**Files:**
- Create: `evals/offline.py`
- Test: `backend/tests/unit/test_offline_evaluation.py`

**Interfaces:**
- `load_cases(path: Path) -> list[dict[str, Any]]` loads JSONL and rejects malformed/non-object records.
- `validate_cases(cases: list[dict[str, Any]]) -> list[str]` requires nonempty unique IDs, `approved: true`, nonempty query/model/prompt values, a `model_stream` replay hash, and a dictionary configuration.
- `write_result_artifact(path: Path, payload: dict[str, Any]) -> Path` atomically writes once and raises `FileExistsError` if the final path already exists.
- `async run_offline_case(case: dict[str, Any], *, archive_root: Path, output_dir: Path, code_revision: str | None, working_tree_dirty: bool) -> dict[str, Any]` runs one replay case and writes its artifact.
- `run_offline_cases(cases_path: Path, *, archive_root: Path, output_dir: Path) -> tuple[list[dict[str, Any]], int]` validates and executes every case, returning artifact summaries and an exit code.

- [ ] **Step 1: Implement strict case loading and validation**

Reject malformed JSONL, missing/duplicate IDs, unapproved cases, absent model ID or prompt version, nonempty query violations, missing `replay_snapshots.model_stream`, invalid 64-hex replay hashes, and non-dictionary configuration. Do not continue into a live runtime when validation fails.

- [ ] **Step 2: Implement revision and timestamp metadata**

Reuse the existing subprocess-based revision pattern from `evals/run.py`, and record both revision and whether the worktree is dirty. Generate UTC ISO timestamps at case start and completion.

- [ ] **Step 3: Build the runtime exclusively through replay resources**

Create `ProviderArchive(archive_root)`, call `build_runtime_resources(provider_archive=archive, replay_snapshots=case["replay_snapshots"])`, construct `FinancialToolRunner(resources)`, and construct `AgentLoop` with `AgentLoopConfig(model=case["model_id"], mode=configuration mode, publish_reports=True)`. Do not pass live clients and do not call `build_runtime_resources` without replay hashes.

- [ ] **Step 4: Capture typed runtime events**

Iterate `AgentLoop.run(...)` with one user `Message`. Concatenate `TextDelta.text` into `report`; capture `RunCompleted.terminal_status`; collect `SkillSelected` versions; and append serialized `RunFailed`, `RunCancelled`, `ProviderFailed`, and `ToolFailed` data to `failure_details`. Preserve partial report text if an exception occurs.

- [ ] **Step 5: Write success and failure artifacts through the same immutable path**

Build the result contract from the case metadata, replay hashes, runtime observations, configuration, report, status, timestamps, and failure details. Catch setup/replay/runtime exceptions into a failed artifact, then return a nonzero contribution. Never substitute a fixture result or omit a failed case.

- [ ] **Step 6: Implement the CLI entry point**

Add arguments:

```text
--cases PATH
--archive-root PATH
--output-dir PATH
```

The command must have no `--live` option and should print one compact JSON summary per case plus return exit code 1 if any case artifact is failed or validation fails.

- [ ] **Step 7: Run focused tests to verify GREEN**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest backend/tests/unit/test_offline_evaluation.py -q -o addopts=''
```

Expected: all offline command tests pass, including failure and immutability cases.

### Task 3: Run full verification and inspect scope

**Files:**
- No additional source files.

- [ ] **Step 1: Run the full backend suite**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest backend/tests -q
```

Expected: all tests pass, with any existing warnings reported unchanged.

- [ ] **Step 2: Run lint and type checks**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run ruff check backend/ evals/
UV_CACHE_DIR=.uv-cache uv run mypy backend/
```

Expected: both commands exit 0.

- [ ] **Step 3: Run the command help without providers**

Run:

```bash
PYTHONPATH=.:backend UV_CACHE_DIR=.uv-cache uv run python -m evals.offline --help
```

Expected: help exits 0 and lists only offline case/archive/output arguments.

- [ ] **Step 4: Review the final diff**

Confirm only `evals/offline.py` and its focused tests changed for this task, no live evaluation path was altered, no network command ran, and no fixture result was created.

## Self-review

- Failed cases are materialized as failed artifacts and surfaced through the exit code.
- Missing cases and duplicate IDs fail validation instead of being silently skipped.
- Artifact immutability is enforced at the final path.
- Replay hashes and source hashes are recorded as provenance identifiers only; they do not prove semantic support or financial correctness.
- Existing scoring in `evals/run.py` and live-provider paths remain separate.
