# Research Pipeline Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current shallow, brittle research phase with an evidence-first, schema-enforced, fault-tolerant research pipeline that blocks unsupported conclusions and exposes explicit insufficiency states.

**Architecture:** The work is split into bounded phases: first stabilize contracts and runtime/prompt mismatches, then introduce canonical evidence and citation schemas, then refactor research agents to produce structured findings, and finally harden orchestration, quality gates, observability, and evaluation. The plan avoids a big-bang rewrite by keeping the LangGraph skeleton while replacing weak internals with typed data contracts and evidence-aware control flow.

**Tech Stack:** FastAPI, LangGraph, Pydantic v2, llama.cpp OpenAI-compatible API, pytest, Ruff, existing `backend/` orchestration and agent modules.

---

## File Structure Map

### Existing files to modify

- `backend/agents/financial/research/research_plan_node.py`
  Purpose: replace static task templates with evidence-gap-driven task planning.
- `backend/agents/financial/research/research_execution_node.py`
  Purpose: enforce required-agent completion rules, partial-failure handling, and structured execution telemetry.
- `backend/agents/financial/analysis/fundamental.py`
  Purpose: migrate from prompt/tool mismatch to schema-bound evidence-first output.
- `backend/agents/financial/analysis/technical.py`
  Purpose: same as fundamental for technical outputs.
- `backend/agents/financial/analysis/sentiment.py`
  Purpose: stop using nonexistent tools and consume canonical evidence retrieval.
- `backend/agents/financial/analysis/macro.py`
  Purpose: replace freeform prompt-only behavior with structured evidence interpretation.
- `backend/agents/financial/analysis/contrarian.py`
  Purpose: implement adversarial risk review over verified claims/evidence.
- `backend/agents/quality/synthesis_node.py`
  Purpose: synthesize structured claims instead of keyword heuristics.
- `backend/agents/quality/critic_node.py`
  Purpose: turn critique into claim-level verification and targeted re-research routing.
- `backend/agents/quality/conflict_resolution_node.py`
  Purpose: replace placeholder resolution with real arbitration output.
- `backend/agents/orchestration/validation_node.py`
  Purpose: enforce strict output gates beyond shape-only validation.
- `backend/app/core/tools/tool_system.py`
  Purpose: remove prompt/runtime mismatches, add canonical research tool metadata, and provide typed failure modes until graph-native tools replace this layer.
- `backend/app/core/contracts/tool_result.py`
  Purpose: carry provenance, warnings, partial-state, and retry metadata instead of just extracted numbers.
- `backend/app/core/orchestration_schemas.py`
  Purpose: add schemas for evidence, findings, claims, citations, conflicts, coverage, and research outcomes.
- `backend/app/core/graph/router_policy.py`
  Purpose: route based on evidence sufficiency, required agent completion, and verification status.
- `backend/app/services/llm_interface.py`
  Purpose: formalize structured generation options used by schema-bound agents.
- `backend/app/services/llama_cpp_service.py`
  Purpose: support response-format and observability improvements for structured agent outputs.
- `backend/config/prompts/*.yaml`
  Purpose: converge on one canonical prompt per agent and remove dead/misleading prompt paths.

### New files to create

- `backend/app/core/research_schemas.py`
  Purpose: canonical Pydantic models for `EvidenceRecord`, `CitationRecord`, `FindingRecord`, `ClaimRecord`, `CoverageReport`, `ResearchAgentResult`, and `ResearchSynthesisResult`.
- `backend/app/core/research_errors.py`
  Purpose: typed error codes, severities, retryability, and hard-stop conditions.
- `backend/app/core/research_quality.py`
  Purpose: evidence sufficiency scoring, source diversity checks, and quality gate helpers.
- `backend/app/core/research_tracing.py`
  Purpose: shared telemetry payload builders for tool calls, retries, insufficiency states, and gating failures.
- `backend/agents/quality/claim_verifier.py`
  Purpose: validate claim-to-citation links and evidence sufficiency.
- `backend/agents/quality/conflict_arbitrator.py`
  Purpose: compare conflicting claims and produce explicit resolved/unresolved arbitration records.
- `backend/tests/unit/core/test_research_schemas.py`
  Purpose: lock canonical schemas.
- `backend/tests/unit/core/test_research_quality.py`
  Purpose: test sufficiency, diversity, and gating logic.
- `backend/tests/unit/agents/test_research_plan_node.py`
  Purpose: validate evidence-gap-driven planning behavior.
- `backend/tests/unit/agents/test_research_execution_node.py`
  Purpose: validate required-agent handling and partial failures.
- `backend/tests/unit/agents/test_fundamental_analysis_node.py`
  Purpose: verify schema-bound output and explicit insufficiency.
- `backend/tests/unit/agents/test_sentiment_analysis_node.py`
  Purpose: verify canonical retrieval path and low-evidence handling.
- `backend/tests/unit/agents/test_synthesis_node.py`
  Purpose: verify structured synthesis from claims.
- `backend/tests/unit/agents/test_critic_node.py`
  Purpose: verify targeted retries and hard-stop conditions.
- `backend/tests/unit/agents/test_validation_node.py`
  Purpose: verify blocking behavior for unsupported major conclusions.
- `backend/tests/integration/test_research_pipeline_hardening.py`
  Purpose: end-to-end regression suite for the redesigned research phase.

## Workstreams

This is one program with six dependent workstreams:

1. Contract stabilization
2. Canonical evidence/citation model
3. Research tool hardening
4. Agent refactors
5. Synthesis/critique/validation hardening
6. Observability and end-to-end verification

### Task 1: Freeze the Current Failure Surface With Tests

**Files:**
- Test: `backend/tests/unit/agents/test_research_plan_node.py`
- Test: `backend/tests/unit/agents/test_research_execution_node.py`
- Test: `backend/tests/unit/agents/test_validation_node.py`

- [ ] **Step 1: Write the failing planning test for static-template behavior that must be replaced**

```python
import pytest

from agents.financial.research.research_plan_node import research_plan_node


@pytest.mark.asyncio
async def test_research_plan_node_marks_missing_evidence_dimensions_in_tasks(monkeypatch):
    state = {
        "goal": {"ticker": "INFY", "objective": "Assess INFY earnings risk"},
        "user_query": "Assess INFY earnings risk",
        "approved_agents": ["fundamental_analysis", "sentiment_analysis"],
        "fetched_data": {
            "fundamentals": {"by_symbol": {"INFY": {"marketCap": 1}}},
            "news": {},
        },
        "data_status": {
            "fundamentals": {"available": True, "coverage": 0.2, "freshness": 0.9},
            "news": {"available": False, "coverage": 0.0, "freshness": 0.0},
        },
        "hypotheses": [
            {"id": "h1", "statement": "Earnings quality may be weakening", "priority": "P0"}
        ],
        "confidence_score": 0.6,
    }

    result = await research_plan_node(state)

    assert result["status"] == "success"
    assert result["tasks"]
    assert any("missing_dimensions" in task["parameters"] for task in result["tasks"])
    assert any(task["parameters"].get("research_question") for task in result["tasks"])
```

- [ ] **Step 2: Run planning test to verify it fails**

Run: `pytest backend/tests/unit/agents/test_research_plan_node.py::test_research_plan_node_marks_missing_evidence_dimensions_in_tasks -v`
Expected: FAIL because current tasks are static and do not include `missing_dimensions` or `research_question`.

- [ ] **Step 3: Write the failing execution test for required-agent enforcement**

```python
import pytest

from agents.financial.research.research_execution_node import research_execution_node


@pytest.mark.asyncio
async def test_research_execution_blocks_when_required_agent_payload_missing(monkeypatch):
    async def fake_fundamental(_state, _resources):
        return {"errors": ["tool unavailable"]}

    monkeypatch.setattr(
        "agents.financial.research.research_execution_node.AGENT_NODE_MAP",
        {"fundamental_analysis": fake_fundamental},
    )

    state = {
        "tasks": [{"task_id": "fundamental_analysis", "agent": "fundamental_analysis", "priority": "P0", "parameters": {}}],
        "approved_agents": ["fundamental_analysis"],
        "timeouts": {"task_timeout_s": 1.0, "stage_timeout_s": 1.0},
    }

    result = await research_execution_node(state)

    assert result["status"] == "failure"
    assert any("required agent" in error.lower() for error in result["errors"])
    assert result["next_action"] == "terminate_failure"
```

- [ ] **Step 4: Run execution test to verify it fails**

Run: `pytest backend/tests/unit/agents/test_research_execution_node.py::test_research_execution_blocks_when_required_agent_payload_missing -v`
Expected: FAIL because current node returns partial success instead of blocking.

- [ ] **Step 5: Write the failing validation test for unsupported major conclusions**

```python
import pytest

from agents.orchestration.validation_node import validation_node


@pytest.mark.asyncio
async def test_validation_node_blocks_major_claim_without_verified_support():
    state = {
        "results": {
            "synthesis": {
                "decision": "buy",
                "key_drivers": ["earnings momentum"],
                "risks": [],
                "data_used": {"fundamentals": {"available": True}},
                "insufficiency_markers": [],
                "claims": [
                    {
                        "claim_id": "c_major",
                        "text": "INFY should be bought now",
                        "importance": "major",
                        "evidence_refs": [],
                    }
                ],
            }
        },
        "confidence_score": 0.88,
        "claim_verification": {"verified_claim_ids": []},
    }

    result = await validation_node(state)

    assert result["status"] == "failure"
    assert any("major" in error.lower() for error in result["errors"])
```

- [ ] **Step 6: Run validation test to verify it fails**

Run: `pytest backend/tests/unit/agents/test_validation_node.py::test_validation_node_blocks_major_claim_without_verified_support -v`
Expected: FAIL because current validation only checks non-empty evidence refs.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/unit/agents/test_research_plan_node.py backend/tests/unit/agents/test_research_execution_node.py backend/tests/unit/agents/test_validation_node.py
git commit -m "test(research): pin shallow pipeline failure modes"
```

### Task 2: Introduce Canonical Research Schemas

**Files:**
- Create: `backend/app/core/research_schemas.py`
- Modify: `backend/app/core/orchestration_schemas.py:121-174`
- Test: `backend/tests/unit/core/test_research_schemas.py`

- [ ] **Step 1: Write the failing schema test**

```python
from pydantic import ValidationError
import pytest

from app.core.research_schemas import EvidenceRecord, ResearchAgentResult


def test_research_agent_result_requires_explicit_status_and_findings():
    with pytest.raises(ValidationError):
        ResearchAgentResult.model_validate({"agent": "fundamental_analysis"})


def test_evidence_record_requires_provenance_fields():
    with pytest.raises(ValidationError):
        EvidenceRecord.model_validate({"text": "missing provenance"})
```

- [ ] **Step 2: Run schema test to verify it fails**

Run: `pytest backend/tests/unit/core/test_research_schemas.py -v`
Expected: FAIL because `research_schemas.py` does not exist.

- [ ] **Step 3: Write minimal canonical schema implementation**

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CitationRecord(BaseModel):
    citation_id: str
    source_type: Literal["news", "filing", "transcript", "structured_data", "macro"]
    source_label: str
    published_at: datetime | None = None
    retrieved_at: datetime
    trust_tier: int = Field(ge=1, le=5)
    relevance_score: float = Field(ge=0.0, le=1.0)
    freshness_score: float = Field(ge=0.0, le=1.0)


class EvidenceRecord(BaseModel):
    evidence_id: str
    citation: CitationRecord
    text: str = Field(min_length=1)
    coverage_tags: list[str] = Field(default_factory=list)
    parse_quality: float = Field(ge=0.0, le=1.0)


class FindingRecord(BaseModel):
    finding_id: str
    dimension: str
    summary: str
    evidence_ids: list[str] = Field(min_length=1)
    unresolved: bool = False


class ClaimRecord(BaseModel):
    claim_id: str
    text: str
    importance: Literal["major", "supporting", "minor"]
    evidence_refs: list[str] = Field(default_factory=list)
    contradicted_by: list[str] = Field(default_factory=list)


class CoverageReport(BaseModel):
    required_dimensions: list[str]
    covered_dimensions: list[str]
    missing_dimensions: list[str]
    source_diversity_score: float = Field(ge=0.0, le=1.0)
    evidence_strength_score: float = Field(ge=0.0, le=1.0)


class ResearchAgentResult(BaseModel):
    agent: str
    status: Literal["ok", "insufficient_evidence", "failed"]
    findings: list[FindingRecord]
    claims: list[ClaimRecord]
    risks: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    citations: list[CitationRecord] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
```

- [ ] **Step 4: Run schema tests to verify they pass**

Run: `pytest backend/tests/unit/core/test_research_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/research_schemas.py backend/app/core/orchestration_schemas.py backend/tests/unit/core/test_research_schemas.py
git commit -m "feat(research): add canonical evidence and claim schemas"
```

### Task 3: Add Typed Research Errors and Quality Gates

**Files:**
- Create: `backend/app/core/research_errors.py`
- Create: `backend/app/core/research_quality.py`
- Test: `backend/tests/unit/core/test_research_quality.py`

- [ ] **Step 1: Write failing tests for explicit hard-stop and retry conditions**

```python
from app.core.research_quality import evaluate_research_gate


def test_research_gate_blocks_major_claim_without_support():
    gate = evaluate_research_gate(
        required_agents=["fundamental_analysis"],
        completed_agents=["fundamental_analysis"],
        major_claim_count=1,
        verified_major_claim_count=0,
        evidence_strength=0.9,
        source_diversity=0.9,
        unresolved_conflicts=0,
    )

    assert gate.status == "hard_stop"
    assert gate.code == "MAJOR_CLAIM_UNSUPPORTED"


def test_research_gate_retries_when_source_diversity_is_too_low():
    gate = evaluate_research_gate(
        required_agents=["fundamental_analysis", "sentiment_analysis"],
        completed_agents=["fundamental_analysis", "sentiment_analysis"],
        major_claim_count=1,
        verified_major_claim_count=1,
        evidence_strength=0.75,
        source_diversity=0.2,
        unresolved_conflicts=0,
    )

    assert gate.status == "retry"
    assert gate.retryable is True
```

- [ ] **Step 2: Run quality tests to verify they fail**

Run: `pytest backend/tests/unit/core/test_research_quality.py -v`
Expected: FAIL because quality gate module does not exist.

- [ ] **Step 3: Implement typed gate result and error codes**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchGateResult:
    status: str
    code: str
    message: str
    retryable: bool


def evaluate_research_gate(*, required_agents, completed_agents, major_claim_count, verified_major_claim_count, evidence_strength, source_diversity, unresolved_conflicts):
    missing_agents = [agent for agent in required_agents if agent not in completed_agents]
    if missing_agents:
        return ResearchGateResult("hard_stop", "REQUIRED_AGENT_MISSING", f"Missing required agents: {missing_agents}", False)
    if major_claim_count > verified_major_claim_count:
        return ResearchGateResult("hard_stop", "MAJOR_CLAIM_UNSUPPORTED", "Major claims must be verified before synthesis can pass.", False)
    if unresolved_conflicts > 0:
        return ResearchGateResult("hard_stop", "UNRESOLVED_CONFLICT", "Conflicting major claims remain unresolved.", False)
    if source_diversity < 0.4:
        return ResearchGateResult("retry", "SOURCE_DIVERSITY_LOW", "Source diversity below threshold.", True)
    if evidence_strength < 0.65:
        return ResearchGateResult("retry", "EVIDENCE_STRENGTH_LOW", "Evidence strength below threshold.", True)
    return ResearchGateResult("pass", "OK", "Research quality gate passed.", False)
```

- [ ] **Step 4: Run quality tests to verify they pass**

Run: `pytest backend/tests/unit/core/test_research_quality.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/research_errors.py backend/app/core/research_quality.py backend/tests/unit/core/test_research_quality.py
git commit -m "feat(research): add typed error and quality gate framework"
```

### Task 4: Repair Prompt Catalog and Runtime Mismatch

**Files:**
- Modify: `backend/config/prompts/technical.yaml`
- Modify: `backend/config/prompts/sentiment.yaml`
- Modify: `backend/config/prompts/macro.yaml`
- Modify: `backend/config/prompts/contrarian.yaml`
- Modify: `backend/agents/financial/analysis/fundamental.py`
- Modify: `backend/agents/financial/analysis/technical.py`
- Modify: `backend/agents/financial/analysis/sentiment.py`
- Modify: `backend/agents/financial/analysis/macro.py`
- Modify: `backend/agents/financial/analysis/contrarian.py`
- Test: `backend/tests/unit/agents/test_fundamental_analysis_node.py`
- Test: `backend/tests/unit/agents/test_sentiment_analysis_node.py`

- [ ] **Step 1: Write failing test that agent prompt references only registered tools or no tools**

```python
from app.core.tools.tool_system import tool_registry
from app.core.prompts import prompt_manager


def test_sentiment_prompt_and_runtime_use_registered_tool_names_only():
    prompt = prompt_manager.get_prompt("sentiment.system")
    assert "qdrant_search_vector_db" not in prompt
    assert "run_finbert_analysis" not in prompt
    available_tool_names = {tool.name for tool in tool_registry.list_tools()}
    assert "submit_sentiment" in available_tool_names
```

- [ ] **Step 2: Run prompt/runtime mismatch tests to verify they fail**

Run: `pytest backend/tests/unit/agents/test_sentiment_analysis_node.py -v`
Expected: FAIL because prompts still reference nonexistent tools and runtime ignores canonical prompt files.

- [ ] **Step 3: Replace hardcoded agent prompts with canonical prompt-manager lookups and strict JSON schemas**

```python
system_prompt = prompt_manager.get_prompt("sentiment.system")
user_prompt = prompt_manager.get_prompt(
    "sentiment.user_node",
    text=params["text"],
)

response = await resources.llm_service.generate_message(
    messages=[
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_prompt),
    ],
    model=MODEL_REASONING,
    response_format={"type": "json_object"},
)
```

- [ ] **Step 4: Update prompt YAML files so every runtime prompt includes success criteria, insufficiency rules, and stop conditions**

```yaml
system: |
  You are the Sentiment Research Agent.
  Return strict JSON only.

  You must:
  1. Use only the provided evidence text.
  2. Produce findings, claims, risks, missing_evidence, and confidence.
  3. Return status="insufficient_evidence" when the evidence is stale, sparse, or off-topic.
  4. Never invent citations or unsupported directional recommendations.
```

- [ ] **Step 5: Run prompt/agent tests to verify they pass**

Run: `pytest backend/tests/unit/agents/test_fundamental_analysis_node.py backend/tests/unit/agents/test_sentiment_analysis_node.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/config/prompts/technical.yaml backend/config/prompts/sentiment.yaml backend/config/prompts/macro.yaml backend/config/prompts/contrarian.yaml backend/agents/financial/analysis/fundamental.py backend/agents/financial/analysis/technical.py backend/agents/financial/analysis/sentiment.py backend/agents/financial/analysis/macro.py backend/agents/financial/analysis/contrarian.py
git commit -m "fix(research): align runtime agents with canonical prompt contracts"
```

### Task 5: Upgrade Tool Contracts for Provenance and Failure Semantics

**Files:**
- Modify: `backend/app/core/tools/tool_system.py`
- Modify: `backend/app/core/contracts/tool_result.py`
- Test: `backend/tests/unit/core/test_tool_result.py`

- [ ] **Step 1: Write failing tests for partial/retryable tool failures and provenance metadata**

```python
from app.core.contracts.tool_result import ToolResult


def test_tool_result_supports_warnings_and_retry_metadata():
    result = ToolResult(
        tool_name="research:retrieve_news_evidence",
        input_parameters={"ticker": "INFY"},
        output_data={"items": []},
        warnings=["NO_RECENT_ARTICLES"],
        partial=True,
        retryable=True,
        trace_id="trace-1",
    )

    assert result.partial is True
    assert result.retryable is True
    assert result.trace_id == "trace-1"
```

- [ ] **Step 2: Run tool-result tests to verify they fail**

Run: `pytest backend/tests/unit/core/test_tool_result.py -v`
Expected: FAIL because current `ToolResult` lacks these fields.

- [ ] **Step 3: Extend `ToolResult` and tool execution responses**

```python
class ToolResult(BaseModel):
    tool_name: str
    input_parameters: dict[str, Any] = Field(default_factory=dict)
    output_data: Any
    extracted_metrics: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    partial: bool = False
    retryable: bool = False
    trace_id: str | None = None
    source_count: int = 0
    quality_score: float | None = None
```

- [ ] **Step 4: Add a startup assertion that prompt-declared tool names exist in the registry**

```python
def assert_prompt_tool_catalog_valid(prompt_tool_names: set[str], available_tool_names: set[str]) -> None:
    missing = sorted(prompt_tool_names - available_tool_names)
    if missing:
        raise RuntimeError(f"Prompt references undefined tools: {missing}")
```

- [ ] **Step 5: Run tool system tests to verify they pass**

Run: `pytest backend/tests/unit/core/test_tool_result.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/tools/tool_system.py backend/app/core/contracts/tool_result.py backend/tests/unit/core/test_tool_result.py
git commit -m "feat(research): add provenance-rich tool result contract"
```

### Task 6: Replace Static Research Planning With Evidence-Gap Planning

**Files:**
- Modify: `backend/agents/financial/research/research_plan_node.py`
- Modify: `backend/agents/shared/utils.py`
- Test: `backend/tests/unit/agents/test_research_plan_node.py`

- [ ] **Step 1: Define a task payload shape driven by research questions and missing dimensions**

```python
task = {
    "task_id": "fundamental_analysis:profitability",
    "agent": "fundamental_analysis",
    "priority": "P0",
    "parameters": {
        "ticker": ticker,
        "research_question": "Is profitability deteriorating?",
        "required_dimensions": ["profitability", "earnings_quality"],
        "missing_dimensions": ["earnings_quality"],
        "minimum_citation_count": 2,
        "verification_focus": "earnings_risk",
    },
}
```

- [ ] **Step 2: Run targeted planning tests**

Run: `pytest backend/tests/unit/agents/test_research_plan_node.py -v`
Expected: FAIL until planner emits these new fields.

- [ ] **Step 3: Implement planner logic that maps hypotheses + data_status -> targeted tasks**

```python
def _derive_required_dimensions(hypotheses: list[dict[str, Any]]) -> list[str]:
    dimensions = []
    for hypothesis in hypotheses:
        statement = str(hypothesis.get("statement", "")).lower()
        if "fundamental" in statement or "earnings" in statement:
            dimensions.extend(["profitability", "valuation", "balance_sheet"])
        if "macro" in statement:
            dimensions.append("macro_regime")
        if "sentiment" in statement or "news" in statement:
            dimensions.append("qualitative_sentiment")
    return sorted(set(dimensions))
```

- [ ] **Step 4: Verify planner tests pass**

Run: `pytest backend/tests/unit/agents/test_research_plan_node.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agents/financial/research/research_plan_node.py backend/agents/shared/utils.py backend/tests/unit/agents/test_research_plan_node.py
git commit -m "feat(research): plan tasks from evidence gaps instead of static templates"
```

### Task 7: Refactor Research Agents to Return `ResearchAgentResult`

**Files:**
- Modify: `backend/agents/financial/analysis/fundamental.py`
- Modify: `backend/agents/financial/analysis/technical.py`
- Modify: `backend/agents/financial/analysis/sentiment.py`
- Modify: `backend/agents/financial/analysis/macro.py`
- Modify: `backend/agents/financial/analysis/contrarian.py`
- Test: `backend/tests/unit/agents/test_fundamental_analysis_node.py`
- Test: `backend/tests/unit/agents/test_sentiment_analysis_node.py`

- [ ] **Step 1: Write failing tests for explicit insufficiency instead of free-text fallback**

```python
import pytest

from agents.financial.analysis.fundamental import fundamental_analysis_node


@pytest.mark.asyncio
async def test_fundamental_agent_returns_insufficient_evidence_when_required_data_missing(fake_resources):
    state = {"current_step": {"parameters": {"ticker": "INFY", "raw_data": {}}}}

    result = await fundamental_analysis_node(state, fake_resources)

    payload = result["agent_outputs"]["fundamental_analysis"]
    assert payload["status"] == "insufficient_evidence"
    assert payload["missing_evidence"]
    assert payload["claims"] == []
```

- [ ] **Step 2: Run agent tests to verify they fail**

Run: `pytest backend/tests/unit/agents/test_fundamental_analysis_node.py backend/tests/unit/agents/test_sentiment_analysis_node.py -v`
Expected: FAIL because current nodes emit ad hoc dicts and free-text fallback payloads.

- [ ] **Step 3: Update each agent to build findings and claims from structured inputs and deterministic outputs**

```python
agent_result = ResearchAgentResult(
    agent="fundamental_analysis",
    status="insufficient_evidence" if not findings else "ok",
    findings=findings,
    claims=claims,
    risks=risks,
    missing_evidence=missing_evidence,
    citations=citations,
    confidence=0.35 if missing_evidence else 0.78,
)

return build_node_success(
    agent_output_key="fundamental_analysis",
    agent_output=agent_result.model_dump(mode="json"),
    tool_name="analysis:fundamental_analysis_result",
    input_parameters=params,
    tool_output=agent_result.model_dump(mode="json"),
)
```

- [ ] **Step 4: Ensure contrarian analysis consumes verified claims and emits unresolved conflicts explicitly**

```python
ClaimRecord(
    claim_id="contrarian_claim_1",
    text="Management guidance may be overstating near-term demand strength.",
    importance="major",
    evidence_refs=["cit_earnings_call_1"],
    contradicted_by=["fundamental_claim_2"],
)
```

- [ ] **Step 5: Run agent tests to verify they pass**

Run: `pytest backend/tests/unit/agents/test_fundamental_analysis_node.py backend/tests/unit/agents/test_sentiment_analysis_node.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/agents/financial/analysis/fundamental.py backend/agents/financial/analysis/technical.py backend/agents/financial/analysis/sentiment.py backend/agents/financial/analysis/macro.py backend/agents/financial/analysis/contrarian.py backend/tests/unit/agents/test_fundamental_analysis_node.py backend/tests/unit/agents/test_sentiment_analysis_node.py
git commit -m "feat(research): make domain agents emit evidence-first results"
```

### Task 8: Harden Research Execution and Partial Failure Handling

**Files:**
- Modify: `backend/agents/financial/research/research_execution_node.py`
- Modify: `backend/app/core/graph/router_policy.py`
- Test: `backend/tests/unit/agents/test_research_execution_node.py`

- [ ] **Step 1: Add failing tests for required vs optional agent semantics**

```python
def test_router_requires_required_agents_before_synthesis():
    state = {
        "approved_agents": ["fundamental_analysis", "sentiment_analysis"],
        "results": {"fundamental_analysis": {"status": "ok"}},
        "required_agents": ["fundamental_analysis", "sentiment_analysis"],
        "tasks": [],
        "goal": {"ticker": "INFY"},
        "data_status": {"ohlcv": {"available": True, "freshness": 1.0, "coverage": 1.0}, "news": {"available": True, "freshness": 1.0, "coverage": 1.0}, "fundamentals": {"available": True, "freshness": 1.0, "coverage": 1.0}, "macro": {"available": True, "freshness": 1.0, "coverage": 1.0}},
        "timeframe_policy": {},
    }

    assert decide_next_action(state) == "run_research_execution"
```

- [ ] **Step 2: Run execution/router tests to verify they fail**

Run: `pytest backend/tests/unit/agents/test_research_execution_node.py -v`
Expected: FAIL because current routing uses coarse cached-results logic.

- [ ] **Step 3: Modify execution node to record per-agent status and hard-fail on missing required agents**

```python
agent_status[agent] = {
    "status": payload.get("status", "failed"),
    "required": agent in required_agents,
    "errors": result.get("errors", []),
}

if agent in required_agents and payload is None:
    hard_errors.append(f"Required agent '{agent}' produced no payload")
```

- [ ] **Step 4: Run execution/router tests to verify they pass**

Run: `pytest backend/tests/unit/agents/test_research_execution_node.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agents/financial/research/research_execution_node.py backend/app/core/graph/router_policy.py backend/tests/unit/agents/test_research_execution_node.py
git commit -m "fix(research): enforce required-agent completion and partial-failure rules"
```

### Task 9: Replace Heuristic Synthesis With Claim-Based Synthesis

**Files:**
- Modify: `backend/agents/quality/synthesis_node.py`
- Create: `backend/agents/quality/claim_verifier.py`
- Test: `backend/tests/unit/agents/test_synthesis_node.py`

- [ ] **Step 1: Write failing synthesis test for claim-based aggregation**

```python
import pytest

from agents.quality.synthesis_node import synthesis_node


@pytest.mark.asyncio
async def test_synthesis_uses_verified_claims_instead_of_keyword_scanning():
    state = {
        "results": {
            "fundamental_analysis": {
                "status": "ok",
                "claims": [{"claim_id": "c1", "text": "Margins improved", "importance": "major", "evidence_refs": ["cit1"]}],
                "findings": [{"finding_id": "f1", "dimension": "profitability", "summary": "Margins improved", "evidence_ids": ["ev1"], "unresolved": False}],
                "confidence": 0.8,
            },
            "sentiment_analysis": {
                "status": "ok",
                "claims": [{"claim_id": "c2", "text": "Management tone is cautious", "importance": "supporting", "evidence_refs": ["cit2"]}],
                "findings": [],
                "confidence": 0.6,
            },
        },
        "claim_verification": {"verified_claim_ids": ["c1", "c2"]},
    }

    result = await synthesis_node(state)

    assert result["results"]["synthesis"]["claims"]
    assert result["results"]["synthesis"]["decision"] in {"buy", "watchlist", "sell", "no_call"}
    assert "signal_mix" not in result["results"]["synthesis"]["key_drivers"]
```

- [ ] **Step 2: Run synthesis test to verify it fails**

Run: `pytest backend/tests/unit/agents/test_synthesis_node.py -v`
Expected: FAIL because current synthesis uses string keywords and generic claims.

- [ ] **Step 3: Implement synthesis over verified claims and findings**

```python
verified_claim_ids = set(state.get("claim_verification", {}).get("verified_claim_ids", []))
verified_claims = [
    claim
    for agent_result in results.values()
    if isinstance(agent_result, dict)
    for claim in agent_result.get("claims", [])
    if claim.get("claim_id") in verified_claim_ids
]
```

- [ ] **Step 4: Run synthesis tests to verify they pass**

Run: `pytest backend/tests/unit/agents/test_synthesis_node.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agents/quality/synthesis_node.py backend/agents/quality/claim_verifier.py backend/tests/unit/agents/test_synthesis_node.py
git commit -m "feat(research): synthesize from verified claims instead of keywords"
```

### Task 10: Implement Real Critique and Conflict Arbitration

**Files:**
- Modify: `backend/agents/quality/critic_node.py`
- Modify: `backend/agents/quality/conflict_resolution_node.py`
- Create: `backend/agents/quality/conflict_arbitrator.py`
- Test: `backend/tests/unit/agents/test_critic_node.py`

- [ ] **Step 1: Write failing critic tests for targeted retry output**

```python
import pytest

from agents.quality.critic_node import critic_node


@pytest.mark.asyncio
async def test_critic_requests_targeted_rerearch_for_invalid_citation_links():
    state = {
        "results": {
            "synthesis": {
                "claims": [{"claim_id": "c1", "text": "Claim", "importance": "major", "evidence_refs": ["missing_ref"]}],
                "decision": "buy",
                "data_used": {},
            }
        },
        "tool_registry": [],
        "confidence_score": 0.8,
        "tasks": [{"task_id": "sentiment_analysis", "agent": "sentiment_analysis", "priority": "P1", "parameters": {}}],
    }

    result = await critic_node(state)

    assert result["critic_decision"] == "retry"
    assert result["force_replan"] is True
    assert any(task["parameters"].get("verification_focus") for task in result["replanned_tasks"])
```

- [ ] **Step 2: Run critic tests to verify they fail**

Run: `pytest backend/tests/unit/agents/test_critic_node.py -v`
Expected: FAIL because current critic uses heuristic evidence extraction and generic retry prompts.

- [ ] **Step 3: Implement claim-level verification and arbitration records**

```python
claim_verification = verify_claims(
    synthesis_claims=synthesis_claims,
    citation_refs=state.get("citation_index", {}),
    evidence_strength=state.get("evidence_strength", 0.0),
)

if claim_verification.invalid_major_claim_ids:
    decision = "retry"
    correction_prompt = "Re-research the unsupported major claims and attach valid citations."
```

- [ ] **Step 4: Replace fake conflict resolution with explicit resolved/unresolved conflict records**

```python
conflict_record = {
    "resolved": False,
    "method": "claim_arbitration",
    "winning_claim_ids": [],
    "unresolved_claim_pairs": [["c1", "c5"]],
}
```

- [ ] **Step 5: Run critic/conflict tests to verify they pass**

Run: `pytest backend/tests/unit/agents/test_critic_node.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/agents/quality/critic_node.py backend/agents/quality/conflict_resolution_node.py backend/agents/quality/conflict_arbitrator.py backend/tests/unit/agents/test_critic_node.py
git commit -m "feat(research): add claim-level critique and conflict arbitration"
```

### Task 11: Strengthen Validation, Final Gating, and Evaluator Inputs

**Files:**
- Modify: `backend/agents/orchestration/validation_node.py`
- Modify: `backend/agents/quality/evaluator_node.py`
- Modify: `backend/config/prompts/evaluator.yaml`
- Test: `backend/tests/unit/agents/test_validation_node.py`

- [ ] **Step 1: Expand validation tests to block low-diversity and unresolved-conflict outputs**

```python
@pytest.mark.asyncio
async def test_validation_blocks_unresolved_conflict_for_directional_decision():
    state = {
        "results": {
            "synthesis": {
                "decision": "buy",
                "key_drivers": ["valuation"],
                "risks": [],
                "data_used": {},
                "insufficiency_markers": [],
                "claims": [{"claim_id": "c1", "importance": "major", "evidence_refs": ["cit1"]}],
            }
        },
        "claim_verification": {"verified_claim_ids": ["c1"]},
        "conflict_record": {"resolved": False, "unresolved_claim_pairs": [["c1", "c2"]]},
        "confidence_score": 0.9,
    }

    result = await validation_node(state)
    assert result["status"] == "failure"
```

- [ ] **Step 2: Run validation tests to verify they fail**

Run: `pytest backend/tests/unit/agents/test_validation_node.py -v`
Expected: FAIL because current validation ignores unresolved conflicts and diversity.

- [ ] **Step 3: Add gate checks for verified major claims, source diversity, unresolved conflicts, and insufficiency markers**

```python
gate = evaluate_research_gate(
    required_agents=state.get("required_agents", []),
    completed_agents=state.get("completed_agents", []),
    major_claim_count=len(major_claims),
    verified_major_claim_count=len(verified_major_claims),
    evidence_strength=float(state.get("evidence_strength", 0.0)),
    source_diversity=float(state.get("coverage_report", {}).get("source_diversity_score", 0.0)),
    unresolved_conflicts=len(unresolved_conflicts),
)
```

- [ ] **Step 4: Update evaluator prompt so it inspects research trace, not only final output prose**

```yaml
user: |
  USER QUERY:
  {user_query}

  CANDIDATE FINAL OUTPUT:
  {final_output_json}

  RESEARCH QUALITY CONTEXT:
  - critic_decision: {critic_decision}
  - validation_passed: {validation_passed}
  - verified_major_claims: {verified_major_claims}
  - source_diversity_score: {source_diversity_score}
  - unresolved_conflicts: {unresolved_conflicts}
```

- [ ] **Step 5: Run validation/evaluator tests to verify they pass**

Run: `pytest backend/tests/unit/agents/test_validation_node.py backend/tests/unit/test_evaluator_node.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/agents/orchestration/validation_node.py backend/agents/quality/evaluator_node.py backend/config/prompts/evaluator.yaml backend/tests/unit/agents/test_validation_node.py
git commit -m "fix(research): enforce final quality gates before success"
```

### Task 12: Add Telemetry, Pipeline Integration Tests, and Release Verification

**Files:**
- Create: `backend/app/core/research_tracing.py`
- Modify: `backend/agents/financial/research/research_execution_node.py`
- Modify: `backend/agents/quality/critic_node.py`
- Modify: `backend/agents/orchestration/validation_node.py`
- Test: `backend/tests/integration/test_research_pipeline_hardening.py`

- [ ] **Step 1: Write integration test covering success, insufficiency, and hard-stop paths**

```python
import pytest

from app.core.orchestrator import PipelineOrchestrator


@pytest.mark.asyncio
async def test_pipeline_returns_insufficient_data_when_evidence_gates_fail(monkeypatch):
    orchestrator = PipelineOrchestrator()

    events = []
    async for event in orchestrator.execute_query("Analyze INFY with weak evidence"):
        events.append(event)

    assert any(getattr(event, "type", None) == "done" or event.type == "done" for event in events)
```

- [ ] **Step 2: Run integration test to verify it fails**

Run: `pytest backend/tests/integration/test_research_pipeline_hardening.py -v`
Expected: FAIL until telemetry and gating are wired through the full graph.

- [ ] **Step 3: Add shared trace helpers and emit structured telemetry from research nodes**

```python
def build_research_trace_event(*, stage: str, code: str, severity: str, query_id: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": stage,
        "code": code,
        "severity": severity,
        "query_id": query_id,
        "details": details,
    }
```

- [ ] **Step 4: Run full verification suite**

Run: `pytest backend/tests/unit/core/test_research_schemas.py backend/tests/unit/core/test_research_quality.py backend/tests/unit/agents/test_research_plan_node.py backend/tests/unit/agents/test_research_execution_node.py backend/tests/unit/agents/test_fundamental_analysis_node.py backend/tests/unit/agents/test_sentiment_analysis_node.py backend/tests/unit/agents/test_synthesis_node.py backend/tests/unit/agents/test_critic_node.py backend/tests/unit/agents/test_validation_node.py backend/tests/integration/test_research_pipeline_hardening.py -v`
Expected: PASS

- [ ] **Step 5: Run static checks**

Run: `ruff check backend/ && ruff format --check backend/ && mypy backend/`
Expected: all commands exit 0

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/research_tracing.py backend/agents/financial/research/research_execution_node.py backend/agents/quality/critic_node.py backend/agents/orchestration/validation_node.py backend/tests/integration/test_research_pipeline_hardening.py
git commit -m "feat(research): add telemetry and end-to-end hardening coverage"
```

## Delivery Sequence

Implement tasks strictly in order. Do not skip ahead.

1. Freeze failure modes with tests.
2. Add schemas and quality gates.
3. Repair prompt/runtime mismatches before agent refactors.
4. Upgrade tools/contracts before relying on richer outputs.
5. Refactor planner and agents.
6. Replace synthesis/critic/validation heuristics.
7. Finish with telemetry and integration tests.

## Non-Negotiable Rules During Execution

1. No agent may emit a major claim without valid citations.
2. No prompt may reference an unregistered runtime tool.
3. No silent fallback to generic prose when required evidence is missing.
4. `status="insufficient_evidence"` is valid; fake certainty is not.
5. Directional final outputs must fail closed on unresolved major conflicts.
6. Quality-gate failures must be explicit, typed, and observable.

## Self-Review

### Spec coverage

- System design of research agents: covered by Tasks 6, 7, 8, 9, 10.
- Prompt/system redesign: covered by Task 4 and Task 11.
- Tool redesign and contracts: covered by Task 5.
- Coordination/verification/refinement: covered by Tasks 8, 9, 10, 11.
- Shallow behavior root causes: addressed by Tasks 1, 4, 6, 7, 9.
- Explicit errors/warnings/retries/hard stops: covered by Task 3 and Task 11.
- Production hardening/observability: covered by Task 12.

### Placeholder scan

- No `TODO`, `TBD`, or deferred placeholders remain.
- Every task has explicit file paths, test commands, and at least one concrete code sample.

### Type consistency

- Canonical runtime output type is `ResearchAgentResult`.
- Canonical evidence objects are `EvidenceRecord`, `CitationRecord`, `FindingRecord`, `ClaimRecord`, and `CoverageReport`.
- Quality gate function name is `evaluate_research_gate` throughout the plan.
