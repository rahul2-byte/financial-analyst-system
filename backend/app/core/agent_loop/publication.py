"""Deterministic validation and rendering for publishable research reports."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class EvidenceFact(BaseModel):
    """One numeric observation made available to a report draft."""

    model_config = ConfigDict(frozen=True)

    fact_id: str = Field(pattern=r"^[a-zA-Z0-9_.:-]+$")
    value: int | float
    unit: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    instrument: str = Field(min_length=1)
    observed_at: datetime
    quality_status: Literal["verified"]

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float) -> int | float:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("numeric evidence must be finite")
        return value


class ReportCitation(BaseModel):
    citation_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)


class ReportClaim(BaseModel):
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=5000)
    importance: Literal["major", "supporting", "minor"]
    evidence_refs: list[str] = Field(default_factory=list)
    numeric_refs: list[str] = Field(default_factory=list)


class ReportDraft(BaseModel):
    """The only model output accepted as a publishable research report."""

    executive_summary: str = Field(min_length=1, max_length=10000)
    key_drivers: list[str] = Field(min_length=1, max_length=20)
    detailed_analysis: str = Field(min_length=1, max_length=20000)
    risks: list[str] = Field(min_length=1, max_length=20)
    final_view: str = Field(min_length=1, max_length=10000)
    claims: list[ReportClaim] = Field(min_length=1, max_length=100)
    citations: list[ReportCitation] = Field(default_factory=list, max_length=200)


class PublicationError(ValueError):
    """A report draft cannot be released as verified research."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = tuple(dict.fromkeys(reasons))
        super().__init__("; ".join(self.reasons))


_FACT_MARKER = re.compile(r"\[\[fact:([a-zA-Z0-9_.:-]+)\]\]")
_NUMBER = re.compile(r"(?<![A-Za-z])[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:%|\b)")


def parse_report_draft(text: str) -> ReportDraft:
    """Parse the model's complete response without accepting wrapper prose."""
    try:
        value = json.loads(text)
        return ReportDraft.model_validate(value)
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise PublicationError(["structured_report_invalid"]) from exc


def publish_report(
    draft: ReportDraft,
    evidence: dict[str, EvidenceFact],
) -> str:
    """Validate references and render a report using only verified evidence."""
    reasons: list[str] = []
    citation_ids = {citation.citation_id for citation in draft.citations}
    if len(citation_ids) != len(draft.citations):
        reasons.append("duplicate_citation_id")
    claim_ids = {claim.claim_id for claim in draft.claims}
    if len(claim_ids) != len(draft.claims):
        reasons.append("duplicate_claim_id")
    source_ids = {fact.source_id for fact in evidence.values()}
    for citation in draft.citations:
        if citation.source_id not in source_ids:
            reasons.append("citation_source_missing")
    all_text = "\n".join(
        [
            draft.executive_summary,
            *draft.key_drivers,
            draft.detailed_analysis,
            *draft.risks,
            draft.final_view,
        ]
    )
    marker_ids = set(_FACT_MARKER.findall(all_text))
    for claim in draft.claims:
        if claim.importance == "major" and not claim.evidence_refs:
            reasons.append("major_claim_unsupported")
        if any(ref not in citation_ids for ref in claim.evidence_refs):
            reasons.append("claim_citation_missing")
        for fact_id in claim.numeric_refs:
            fact = evidence.get(fact_id)
            if fact is None:
                reasons.append("numeric_fact_missing")
            elif fact_id not in marker_ids:
                reasons.append("numeric_fact_not_rendered")
    for fact_id in marker_ids:
        fact = evidence.get(fact_id)
        if fact is None:
            reasons.append("numeric_fact_missing")
        elif fact.quality_status != "verified":
            reasons.append("numeric_fact_unverified")
    unbound_numbers = _NUMBER.findall(_FACT_MARKER.sub("", all_text))
    if unbound_numbers:
        reasons.append("numeric_claim_unbound")
    if reasons:
        raise PublicationError(reasons)
    return _render(draft, evidence)


def _render(draft: ReportDraft, evidence: dict[str, EvidenceFact]) -> str:
    def replace(text: str) -> str:
        return _FACT_MARKER.sub(
            lambda match: (
                f"{evidence[match.group(1)].value} {evidence[match.group(1)].unit}"
            ),
            text,
        )

    sections = [
        ("Executive Summary", replace(draft.executive_summary)),
        ("Key Drivers", "\n".join(f"- {replace(item)}" for item in draft.key_drivers)),
        ("Detailed Analysis", replace(draft.detailed_analysis)),
        (
            "Risks and Contrarian View",
            "\n".join(f"- {replace(item)}" for item in draft.risks),
        ),
        ("Final View", replace(draft.final_view)),
    ]
    return "\n\n".join(f"## {title}\n{body}" for title, body in sections)
