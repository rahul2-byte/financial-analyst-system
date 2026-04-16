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
