# Frozen Evaluation Pilot Candidate Manifest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define and validate a 20-case candidate evaluation set whose source metadata and human labels remain explicitly pending until supplied by the project owner and independent reviewers.

**Architecture:** Keep `freeze_snapshot` as the only writer for immutable source bytes and keep `validate_human_labels` as the validator for completed independent labels. Add small candidate-record validators beside those workflows, and store a JSONL candidate manifest plus a review handoff document; no real source content, URLs, hashes, or labels are added.

**Tech Stack:** Python 3.11+, stdlib JSONL parsing, pytest, existing `evals` modules.

**Spec:** Approved in-chat bounded design from 2026-09-19.

## Global Constraints

- The pilot contains exactly 20 candidate cases: four each across fundamentals, technical analysis, news/source interpretation, conflicting evidence, and insufficient evidence.
- Candidate cases are not frozen evidence and must not be classified as financial-quality or market-quality evidence.
- Do not invent real source URLs, publishers, retrieval timestamps, permitted-use grants, content hashes, expected labels, or evidence spans.
- Source bytes must later be captured through `freeze_snapshot`; human labels must later be supplied by at least two independent reviewers and adjudicated when they disagree.
- Do not add dependencies, call providers, download models, or alter unrelated evaluation architecture.

## Review Focus

- A candidate with a fabricated or partially populated source record must be rejected; covered by `test_candidate_source_metadata_must_be_pending`.
- Duplicate case IDs must be rejected; covered by `test_candidate_cases_require_unique_ids`.
- Missing expected-evidence or labeling instructions must be rejected; covered by `test_candidate_cases_require_review_fields`.
- The committed manifest must contain all five categories with four cases each; covered by `test_pilot_candidate_manifest_has_balanced_categories`.
- Completed labels remain subject to the existing two-reviewer rules; existing `test_human_labels.py` remains part of the full suite.

### Task 1: Add candidate-manifest and source-placeholder tests

**Files:**
- Create: `backend/tests/unit/test_candidate_evaluation.py`
- Read: `evals/snapshots.py`, `evals/labels.py`, `evals/gold/v1/source-manifest.json`

**Interfaces:**
- Consumes: `validate_candidate_source_record(record: dict[str, Any]) -> list[str]` and `validate_candidate_cases(cases: list[dict[str, Any]], expected_cases: int = 20) -> list[str]`.
- Produces: regression tests for the candidate-only contract and the checked-in 20-case manifest.

- [ ] **Step 1: Write the failing validator tests**

Add tests that assert:

```python
def test_candidate_source_metadata_must_be_pending():
    assert "candidate source must remain unresolved" in validate_candidate_source_record(
        {"status": "candidate", "source_url": "https://example.test"}
    )


def test_candidate_cases_require_unique_ids():
    cases = [{"id": "case-1"}, {"id": "case-1"}]
    assert "case ids must be unique" in validate_candidate_cases(cases, expected_cases=2)


def test_candidate_cases_require_review_fields():
    errors = validate_candidate_cases(
        [{"id": "case-1", "category": "fundamentals"}], expected_cases=1
    )
    assert "expected_evidence" in " ".join(errors)
    assert "labeling_instructions" in " ".join(errors)
```

Add a manifest test that loads `evals/candidates/pilot-v1/cases.jsonl`, validates it, and checks category counts are exactly four each.

- [ ] **Step 2: Run the focused tests to verify RED**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest backend/tests/unit/test_candidate_evaluation.py -q -o addopts=''
```

Expected: collection fails because the two new validator functions do not yet exist.

### Task 2: Implement candidate validators and the 20-case manifest

**Files:**
- Modify: `evals/snapshots.py`
- Modify: `evals/labels.py`
- Create: `evals/candidates/pilot-v1/cases.jsonl`
- Create: `evals/candidates/pilot-v1/README.md`
- Test: `backend/tests/unit/test_candidate_evaluation.py`

**Interfaces:**
- `validate_candidate_source_record(record: dict[str, Any]) -> list[str]` checks that a candidate source has `status: "pending_owner_source"` and all five source fields (`source_url`, `publisher`, `retrieved_at`, `permitted_use`, `sha256`) are `None` or empty; any populated value is rejected as unverified.
- `validate_candidate_cases(cases: list[dict[str, Any]], expected_cases: int = 20) -> list[str]` checks count, unique IDs, allowed categories, nonempty questions, structured `expected_evidence`, nonempty `labeling_instructions`, candidate status, unresolved source metadata, and empty labels.

- [ ] **Step 1: Implement `validate_candidate_source_record`**

Return deterministic errors for a non-candidate status, missing `status`, or any populated source metadata. Do not hash or write bytes in this validator; only `freeze_snapshot` may create immutable snapshots.

- [ ] **Step 2: Implement `validate_candidate_cases`**

Validate the 20-case contract and call `validate_candidate_source_record` for each case’s `source`. Require `labels` to be an empty list and require `expected_evidence` to be a dictionary with a nonempty `status` such as `pending_owner_review`; this records the requirement without inventing evidence.

- [ ] **Step 3: Add the 20 candidate records**

Create four cases per category. Every record must include:

```json
{
  "id": "pilot-v1-fundamentals-01",
  "status": "candidate",
  "category": "fundamentals",
  "source": {
    "source_id": null,
    "source_url": null,
    "publisher": null,
    "retrieved_at": null,
    "permitted_use": null,
    "sha256": null,
    "status": "pending_owner_source"
  },
  "question": "...",
  "expected_evidence": {
    "status": "pending_owner_review",
    "items": []
  },
  "labeling_instructions": "...",
  "labels": []
}
```

Questions must be evidence-seeking prompts, not claims about actual companies, prices, events, or outcomes. Use category-specific instructions that tell reviewers what evidence span and support/contradiction/insufficient-evidence judgment to record.

- [ ] **Step 4: Add the owner/reviewer handoff document**

Document that the project owner must select permitted public sources, capture bytes with `freeze_snapshot`, fill URL/publisher/retrieval/permitted-use/hash fields, define expected evidence, and approve the labeling protocol. Document that two independent reviewers must label evidence spans and judgments, and that disagreements require adjudication. State clearly that the candidate manifest is not a benchmark result.

- [ ] **Step 5: Run focused tests to verify GREEN**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest backend/tests/unit/test_candidate_evaluation.py backend/tests/unit/test_snapshots.py backend/tests/unit/test_human_labels.py -q -o addopts=''
```

Expected: all focused candidate, snapshot, and label tests pass.

### Task 3: Run repository verification and preserve negative results

**Files:**
- No additional source files.

- [ ] **Step 1: Run the full backend test suite**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest backend/tests -q
```

Expected: the suite passes or any pre-existing failure is reported verbatim; the candidate manifest must not be treated as market-quality evidence.

- [ ] **Step 2: Run lint, type, and artifact checks**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run ruff check backend/ evals/
UV_CACHE_DIR=.uv-cache uv run mypy backend/
PYTHONPATH=.:backend UV_CACHE_DIR=.uv-cache uv run python evals/validate.py
```

Expected: lint, types, and the existing 10-case fixture validation pass without changing fixture status.

## Self-review

- The manifest has no real source URLs, source hashes, labels, or evidence spans.
- The validators distinguish candidate metadata from frozen snapshots and completed human labels.
- Existing `evals/gold/v1` remains untouched and remains synthetic-contract-only.
- No provider, model, licensed-data, or paid-API step is required.
