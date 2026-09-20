# Report Citation Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate report-to-source bindings and render claim references plus a compact, URL-backed source list without treating identifier matching as semantic support.

**Architecture:** Keep the existing `ReportDraft` and `EvidenceFact` contracts. Extend `publish_report` with deterministic structural checks that resolve citation IDs, source IDs, source URLs, and numeric fact provenance; extend `_render` to emit rendered claims and deduplicated source metadata. No provider, schema, or orchestration changes are needed.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest.

**Spec:** Approved in-chat bounded design from 2026-09-19.

## Global Constraints

- Preserve all existing structural publication checks.
- Quantitative facts remain deterministic `EvidenceFact` values; the LLM does not calculate or validate them.
- Identifier/source matching proves only structural provenance linkage, not semantic claim support.
- Reject broken citation references rather than rendering incomplete source metadata.
- Do not add dependencies or change unrelated architecture.
- Preserve existing worktree changes outside the publication files.

## Review Focus

- A citation that names a known source but has no URL must be rejected, not rendered as a broken link; covered by `test_publish_report_rejects_citation_without_source_url`.
- A numeric fact whose `source_id` is not among the claim's cited sources must be rejected; covered by `test_publish_report_rejects_numeric_fact_with_unresolved_source`.
- Duplicate citation IDs must preserve the existing rejection; covered by `test_publish_report_rejects_duplicate_citation_ids`.
- Missing citation source IDs must preserve the existing rejection; covered by `test_publish_report_rejects_unknown_source`.
- Valid citations must render claim references and source ID, URL, and timestamp; covered by `test_publish_report_renders_claim_references_and_sources`.

### Task 1: Add failing publication tests

**Files:**
- Modify: `backend/tests/unit/test_publication.py`
- Read: `backend/app/core/agent_loop/publication.py`

**Interfaces:**
- Consumes: `publish_report(draft: ReportDraft, evidence: dict[str, EvidenceFact]) -> str` and existing test helpers.
- Produces: executable expectations for citation rendering and broken-reference rejection.

- [ ] **Step 1: Add a URL to the valid evidence fixture**

Set the existing fixture's `source_url` to `https://example.test/price` so the valid path can assert source metadata without weakening the missing-URL case.

- [ ] **Step 2: Write the valid rendering test**

Add a test that calls `publish_report(_draft(), _evidence())` and asserts the output contains the claim text, `citation-1`, `source:yfinance`, the URL, and the ISO observation timestamp.

- [ ] **Step 3: Write the duplicate-ID test**

Create two citations with the same `citation_id` and assert `PublicationError` contains `duplicate_citation_id`.

- [ ] **Step 4: Write the missing-URL test**

Override the citation to use the known source and leave the fixture URL absent; assert `PublicationError` contains `citation_source_url_missing`.

- [ ] **Step 5: Write the unresolved numeric-source test**

Keep the fact marker and numeric reference, but make the citation point to a different valid source ID than the fact's `source_id`; assert `PublicationError` contains `numeric_fact_source_missing`.

- [ ] **Step 6: Run the focused tests to verify the new tests fail for the missing behavior**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest backend/tests/unit/test_publication.py -q
```

Expected: existing tests pass, while the new rendering and new validation tests fail because `_render` does not yet render claims/sources and `publish_report` does not yet enforce URL or numeric-source binding.

### Task 2: Implement validation and rendering

**Files:**
- Modify: `backend/app/core/agent_loop/publication.py`
- Test: `backend/tests/unit/test_publication.py`

**Interfaces:**
- Consumes: the existing `ReportDraft`, `ReportCitation`, `EvidenceFact`, and evidence dictionary.
- Produces: `publish_report` output with `Claims and references` and `Sources` sections, or `PublicationError` for broken references.

- [ ] **Step 1: Add source-resolution checks**

Build a `source_id -> EvidenceFact` view from the evidence. For every citation, retain the existing missing-source check and add a missing-URL reason when the resolved source has no nonblank `source_url`. Keep reason de-duplication through `PublicationError`.

- [ ] **Step 2: Add numeric-fact source binding checks**

For each `numeric_refs` entry that resolves to an evidence fact, require that fact's `source_id` be among the source IDs resolved by the claim's `evidence_refs`. Emit `numeric_fact_source_missing` when it is not. Do not infer or state semantic support.

- [ ] **Step 3: Render claims with their citation IDs**

After the existing narrative sections, add a `## Claims and references` section. Render each claim's text with fact markers replaced and append its validated citation IDs in brackets. This is a structural reference display only.

- [ ] **Step 4: Render a deduplicated source list**

Add a `## Sources` section containing one line per cited source, sorted by source ID, with source ID, URL, and the evidence observation timestamp in ISO format.

- [ ] **Step 5: Run the focused tests to verify green**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest backend/tests/unit/test_publication.py -q
```

Expected: all publication tests pass, including the pre-existing structural checks.

- [ ] **Step 6: Run the full backend test suite and static checks**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest backend/tests -q
UV_CACHE_DIR=.uv-cache uv run ruff check backend/
UV_CACHE_DIR=.uv-cache uv run mypy backend/
```

Expected: each command exits 0. Report any pre-existing failures separately rather than relabeling them as citation evidence.

## Self-review

- Coverage: valid references, duplicate IDs, missing sources, missing URLs, unresolved numeric sources, existing numeric binding, fallback behavior, and existing structural checks are covered.
- Scope: only the publication module and its unit tests change; no new dependency or provider behavior is introduced.
- Semantics: output wording describes references and source identifiers, not semantic claim validation.
- Negative results: any failing check remains reported with its exact command and result.
