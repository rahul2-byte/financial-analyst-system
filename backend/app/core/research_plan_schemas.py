from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TaskPriority = Literal["P0", "P1", "P2", "P3"]


class StructuredEvidenceRequirements(BaseModel):
    datasets: list[str] = Field(default_factory=list)
    minimum_coverage: float = Field(default=0.5, ge=0.0, le=1.0)
    minimum_freshness: float = Field(default=0.5, ge=0.0, le=1.0)
    required_fields: list[str] = Field(default_factory=list)


class QualitativeEvidenceRequirements(BaseModel):
    enabled: bool = False
    corpus_types: list[str] = Field(default_factory=list)
    query_text: str = ""
    limit: int = Field(default=0, ge=0, le=25)
    recency_window_days: int = Field(default=90, ge=1, le=3650)


class EvidenceSelectionReport(BaseModel):
    query_text: str = ""
    limit: int = Field(default=0, ge=0, le=25)
    returned_count: int = Field(default=0, ge=0)
    corpus_types: list[str] = Field(default_factory=list)
    evidence_source: str = "none"
    failure_reason: str | None = None


class QualitativeEvidenceItem(BaseModel):
    evidence_id: str | None = None
    text: str = Field(min_length=1)
    source: str = "Unknown"
    published_date: str = ""
    source_type: str = "news"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CoverageSnapshot(BaseModel):
    required_dimensions: list[str] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)
    dataset_status: dict[str, dict[str, Any]] = Field(default_factory=dict)


class AgentEvidenceBundle(BaseModel):
    structured_inputs: dict[str, Any] = Field(default_factory=dict)
    qualitative_inputs: list[QualitativeEvidenceItem] = Field(default_factory=list)
    dependency_results: dict[str, Any] = Field(default_factory=dict)
    coverage: CoverageSnapshot = Field(default_factory=CoverageSnapshot)
    evidence_selection: EvidenceSelectionReport = Field(
        default_factory=EvidenceSelectionReport
    )
    warnings: list[str] = Field(default_factory=list)


class AgentExecutionInput(BaseModel):
    agent: str
    ticker: str | None = None
    symbols: list[str] = Field(default_factory=list)
    timeframe: str | None = None
    objective: str = Field(min_length=1)
    research_question: str = Field(min_length=1)
    required_dimensions: list[str] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)
    correction_prompt: str | None = None
    verification_focus: str | None = None
    evidence_bundle: AgentEvidenceBundle = Field(default_factory=AgentEvidenceBundle)


class ResearchTaskSpec(BaseModel):
    task_id: str = Field(min_length=1)
    agent: str = Field(min_length=1)
    priority: TaskPriority = "P1"
    ticker: str | None = None
    symbols: list[str] = Field(default_factory=list)
    timeframe: str | None = None
    # Optional for backwards compatibility: some execution callers pass only
    # {task_id, agent, priority, parameters}.
    objective: str = ""
    research_question: str = ""
    required_dimensions: list[str] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    structured_requirements: StructuredEvidenceRequirements = Field(
        default_factory=StructuredEvidenceRequirements
    )
    qualitative_requirements: QualitativeEvidenceRequirements = Field(
        default_factory=QualitativeEvidenceRequirements
    )
    verification_focus: str | None = None
    correction_prompt: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
