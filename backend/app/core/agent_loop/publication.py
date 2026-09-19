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
    source_url: str | None = None

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


class ResearchAnswerV2(ReportDraft):
    """Structured answer contract used for concise and full research answers."""

    answer_type: Literal["analysis", "report"] = "analysis"


class PublicationError(ValueError):
    """A report draft cannot be released as verified research."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = tuple(dict.fromkeys(reasons))
        super().__init__("; ".join(self.reasons))


_FACT_MARKER = re.compile(r"\[\[fact:([a-zA-Z0-9_.:-]+)\]\]")
_NUMBER = re.compile(r"(?<![A-Za-z])[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:%|\b)")


def parse_report_draft(text: str) -> ResearchAnswerV2:
    """Parse the model's complete response without accepting wrapper prose."""
    try:
        value = json.loads(text)
        return ResearchAnswerV2.model_validate(value)
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
        if not claim.evidence_refs:
            reasons.append("claim_unsupported")
            if claim.importance == "major":
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


_REASON_TEXT = {
    "structured_report_invalid": "The report format was invalid.",
    "major_claim_unsupported": "A main conclusion lacked cited evidence.",
    "numeric_claim_unbound": "A number was not linked to verified data.",
    "numeric_fact_missing": "A cited number was absent from verified data.",
    "citation_source_missing": "A citation did not match a verified source.",
}


def report_validation_fallback(
    evidence: dict[str, EvidenceFact], reasons: tuple[str, ...] = ()
) -> str:
    """Give the user a safe result when a model draft fails publication checks."""
    explanation = " ".join(
        dict.fromkeys(
            _REASON_TEXT.get(reason, "The report failed a verification check.")
            for reason in reasons
        )
    )
    if explanation:
        explanation = " " + explanation
    if not evidence:
        return (
            "I could not verify a publishable report from the available evidence."
            + explanation
            + " "
            "No financial claim or figure was released. Inspect the available "
            "tool and source events for details."
        )
    sources = sorted({fact.source_id for fact in evidence.values()})
    facts = sorted(
        evidence.values(), key=lambda fact: ("latest" not in fact.fact_id, fact.fact_id)
    )[:10]
    observations = "\n".join(
        f"- {fact.fact_id}: {fact.value} {fact.unit} "
        f"({fact.source_id}, observed {fact.observed_at.isoformat()})"
        for fact in facts
    )
    return (
        "## Verified evidence\n"
        "I could not verify a publishable narrative, so this response contains "
        "only deterministic provider observations."
        + explanation
        + "\n\nSources: "
        + ", ".join(sources)
        + ".\n\n"
        + observations
        + "\n\n## Data limitations\n"
        "- The model did not produce a report that passed the evidence-binding checks.\n"
        "- No investment conclusion is provided from this fallback.\n"
        "- Inspect source events and rerun the analysis if a cited source is missing."
    )


def report_repair_instruction(
    evidence: dict[str, EvidenceFact], reasons: tuple[str, ...]
) -> str:
    """Return one bounded correction request after a report-format failure."""
    facts = list(evidence.values())[:80]
    fact_catalog = ", ".join(fact.fact_id for fact in facts) or "none"
    sources = ", ".join(sorted({fact.source_id for fact in facts})) or "none"
    return (
        "Formatting repair required. Your preceding response cannot be published: "
        + ", ".join(reasons)
        + ". Return only the required report JSON now; do not call tools. Use only "
        "these evidence fact IDs for numeric_refs and [[fact:...]] markers: "
        + fact_catalog
        + ". Citation source_id values must be one of: "
        + sources
        + ". Do not state a conclusion that lacks a claim citation."
    )


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
