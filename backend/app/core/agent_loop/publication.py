"""Deterministic validation and rendering for publishable research reports."""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from typing import Annotated, Literal

from app.core.observability import observe
from app.core.prompts import PromptRegistry
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

_FACT_ID_PATTERN = r"^[a-zA-Z0-9_.:-]+$"
_FACT_MARKER = re.compile(r"\[\[fact:([a-zA-Z0-9_.:-]+)\]\]")
FactReference = Annotated[str, Field(pattern=_FACT_ID_PATTERN)]


class EvidenceFact(BaseModel):
    """One verified provider observation made available to a report draft."""

    model_config = ConfigDict(frozen=True)

    fact_id: str = Field(pattern=r"^[a-zA-Z0-9_.:-]+$")
    value: int | float | str
    unit: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    instrument: str = Field(min_length=1)
    observed_at: datetime
    quality_status: Literal["verified"]
    source_url: str | None = None

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float | str) -> int | float | str:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("numeric evidence must be finite")
        return value

    @model_validator(mode="after")
    def validate_provider_date(self) -> EvidenceFact:
        if isinstance(self.value, str):
            if self.unit == "provider_date":
                date.fromisoformat(self.value)
            elif self.unit == "provider_timestamp":
                datetime.fromisoformat(self.value)
            else:
                raise ValueError("text evidence must be an ISO date or timestamp")
        return self


class ReportCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)


class ReportClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=5000)
    importance: Literal["major", "supporting", "minor"]
    evidence_refs: list[str] = Field(default_factory=list)
    numeric_refs: list[FactReference] = Field(
        default_factory=list,
        description="Bare fact IDs, without the [[fact:...]] marker wrappers.",
    )

    @field_validator("numeric_refs", mode="before")
    @classmethod
    def normalize_fact_marker_refs(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        normalized: list[object] = []
        for fact_id in value:
            marker = (
                _FACT_MARKER.fullmatch(fact_id) if isinstance(fact_id, str) else None
            )
            normalized.append(marker.group(1) if marker else fact_id)
        return normalized


class ReportDraft(BaseModel):
    """The only model output accepted as a publishable research report."""

    model_config = ConfigDict(extra="forbid")

    executive_summary: str = Field(min_length=1, max_length=10000)
    key_drivers: list[str] = Field(min_length=1, max_length=20)
    detailed_analysis: str = Field(min_length=1, max_length=20000)
    risks: list[str] = Field(min_length=1, max_length=20)
    final_view: str = Field(min_length=1, max_length=10000)
    claims: list[ReportClaim] = Field(min_length=1, max_length=100)
    citations: list[ReportCitation] = Field(default_factory=list, max_length=200)


class LookupAnswerV1(BaseModel):
    """Compact output contract for a response grounded in one tool result."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["answered", "partial", "insufficient_data"]
    answer: str = Field(min_length=1, max_length=10000)
    claims: list[ReportClaim] = Field(default_factory=list, max_length=50)
    citations: list[ReportCitation] = Field(default_factory=list, max_length=50)
    limitations: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def supported_outcomes_require_claims(self) -> LookupAnswerV1:
        if self.outcome != "insufficient_data" and not self.claims:
            raise ValueError("answered lookup requires at least one claim")
        return self


class ResearchAnswerV2(ReportDraft):
    """Structured answer contract used for concise and full research answers."""

    answer_type: Literal["analysis", "report"] = "analysis"


class PublicationError(ValueError):
    """A report draft cannot be released as verified research."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = tuple(dict.fromkeys(reasons))
        super().__init__("; ".join(self.reasons))


class ReportParseError(PublicationError):
    """The model response is not a report-shaped JSON document."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(["structured_report_invalid", detail])


_NUMBER = re.compile(r"(?<![A-Za-z0-9])[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:%|\b)")
_UNSAFE_GUARANTEE = re.compile(
    r"\b(?:guaranteed?\s+(?:return|profit|gain)|cannot\s+lose|risk[- ]free)\b",
    re.IGNORECASE,
)


@observe("report.parse", as_type="report_parse")
def parse_report_draft(text: str) -> ResearchAnswerV2:
    """Parse the model's complete response without accepting wrapper prose."""
    try:
        value = json.loads(text)
        return ResearchAnswerV2.model_validate(value)
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise ReportParseError(str(exc)) from exc


def parse_lookup_answer(text: str) -> LookupAnswerV1:
    try:
        return LookupAnswerV1.model_validate_json(text)
    except (ValueError, ValidationError) as exc:
        raise ReportParseError(str(exc)) from exc


def unreferenced_fact_markers(draft: ReportDraft) -> tuple[str, ...]:
    all_text = "\n".join(
        [
            draft.executive_summary,
            *draft.key_drivers,
            draft.detailed_analysis,
            *draft.risks,
            draft.final_view,
            *(claim.text for claim in draft.claims),
        ]
    )
    referenced = {fact_id for claim in draft.claims for fact_id in claim.numeric_refs}
    return tuple(sorted(set(_FACT_MARKER.findall(all_text)) - referenced))


def publish_lookup_answer(
    answer: LookupAnswerV1,
    evidence: dict[str, EvidenceFact],
    sources: dict[str, dict[str, str]] | None = None,
) -> str:
    """Fail closed unless each lookup claim and number maps to returned evidence."""
    citation_ids = {citation.citation_id for citation in answer.citations}
    source_records: dict[str, EvidenceFact | dict[str, str]] = {
        key: value for key, value in _source_records(evidence).items()
    }
    source_records.update(sources or {})
    citation_sources = {item.citation_id: item.source_id for item in answer.citations}
    reasons: list[str] = []
    if len(citation_ids) != len(answer.citations):
        reasons.append("duplicate_citation_id")
    if len({claim.claim_id for claim in answer.claims}) != len(answer.claims):
        reasons.append("duplicate_claim_id")
    for citation in answer.citations:
        source = source_records.get(citation.source_id)
        if source is None:
            reasons.append("citation_source_missing")
        elif not _source_url(source):
            reasons.append("citation_source_url_missing")
    all_text = "\n".join(
        [answer.answer, *answer.limitations, *(claim.text for claim in answer.claims)]
    )
    if _UNSAFE_GUARANTEE.search(all_text):
        reasons.append("unsafe_guarantee_claim")
    if answer.outcome != "insufficient_data" and answer.answer not in {
        claim.text for claim in answer.claims
    }:
        reasons.append("lookup_answer_not_claim_backed")
    for claim in answer.claims:
        claim_markers = set(_FACT_MARKER.findall(claim.text))
        if not claim.evidence_refs:
            reasons.append("claim_unsupported")
        if any(ref not in citation_ids for ref in claim.evidence_refs):
            reasons.append("claim_citation_missing")
        supported_sources = {
            citation_sources[ref]
            for ref in claim.evidence_refs
            if ref in citation_sources
        }
        for fact_id in claim.numeric_refs:
            fact = evidence.get(fact_id)
            if fact is None:
                reasons.append("numeric_fact_missing")
            elif fact_id not in claim_markers:
                reasons.append("numeric_fact_not_rendered")
            elif fact.source_id not in supported_sources:
                reasons.append("numeric_fact_source_missing")
    marker_ids = set(_FACT_MARKER.findall(all_text))
    claimed_numeric_refs = {
        fact_id for claim in answer.claims for fact_id in claim.numeric_refs
    }
    if marker_ids - claimed_numeric_refs:
        reasons.append("numeric_fact_reference_missing")
    if any(fact_id not in evidence for fact_id in marker_ids):
        reasons.append("numeric_fact_missing")
    if _NUMBER.findall(_FACT_MARKER.sub("", all_text)):
        reasons.append("numeric_claim_unbound")
    if reasons:
        raise PublicationError(reasons)

    def replace(text: str) -> str:
        return _FACT_MARKER.sub(
            lambda match: _format_fact_value(evidence[match.group(1)]), text
        )

    sections = ["## Answer", replace(answer.answer), "\n## Evidence"]
    sections.extend(
        f"- {replace(claim.text)} [citations: {', '.join(claim.evidence_refs)}]"
        for claim in answer.claims
    )
    if answer.limitations:
        sections.extend(
            ["\n## Limitations", *[f"- {replace(item)}" for item in answer.limitations]]
        )
    cited_source_ids = {citation.source_id for citation in answer.citations}
    source_lines = [
        f"- {_source_display(source_records[source_id])}"
        for source_id in sorted(cited_source_ids)
        if source_id in source_records
    ]
    if source_lines:
        sections.extend(["\n## Sources", *source_lines])
    return "\n".join(sections)


@observe("report.publish", as_type="publication")
def publish_report(
    draft: ReportDraft,
    evidence: dict[str, EvidenceFact],
    sources: dict[str, dict[str, str]] | None = None,
    availability: dict[str, dict[str, object]] | None = None,
) -> str:
    """Validate references and render a report using only verified evidence."""
    reasons: list[str] = []
    citation_ids = {citation.citation_id for citation in draft.citations}
    if len(citation_ids) != len(draft.citations):
        reasons.append("duplicate_citation_id")
    claim_ids = {claim.claim_id for claim in draft.claims}
    if len(claim_ids) != len(draft.claims):
        reasons.append("duplicate_claim_id")
    source_records: dict[str, EvidenceFact | dict[str, str]] = {
        key: value for key, value in _source_records(evidence).items()
    }
    source_records.update(sources or {})
    source_ids = set(source_records)
    citation_sources: dict[str, str] = {}
    for citation in draft.citations:
        if citation.source_id not in source_ids:
            reasons.append("citation_source_missing")
        else:
            citation_sources[citation.citation_id] = citation.source_id
            if not _source_url(source_records[citation.source_id]):
                reasons.append("citation_source_url_missing")
    all_text = "\n".join(
        [
            draft.executive_summary,
            *draft.key_drivers,
            draft.detailed_analysis,
            *draft.risks,
            draft.final_view,
            *(claim.text for claim in draft.claims),
        ]
    )
    marker_ids = set(_FACT_MARKER.findall(all_text))
    claimed_numeric_refs = {
        fact_id for claim in draft.claims for fact_id in claim.numeric_refs
    }
    if marker_ids - claimed_numeric_refs:
        reasons.append("numeric_fact_reference_missing")
    if _UNSAFE_GUARANTEE.search(all_text):
        reasons.append("unsafe_guarantee_claim")
    for claim in draft.claims:
        claim_markers = set(_FACT_MARKER.findall(claim.text))
        if not claim.evidence_refs:
            reasons.append("claim_unsupported")
            if claim.importance == "major":
                reasons.append("major_claim_unsupported")
        if any(ref not in citation_ids for ref in claim.evidence_refs):
            reasons.append("claim_citation_missing")
        claim_source_ids = {
            citation_sources[ref]
            for ref in claim.evidence_refs
            if ref in citation_sources
        }
        if claim.importance == "major" and any(
            isinstance(source, dict) and source.get("quality_status") == "degraded"
            for source in (source_records[source_id] for source_id in claim_source_ids)
        ):
            reasons.append("degraded_source_claim")
        for fact_id in claim.numeric_refs:
            fact = evidence.get(fact_id)
            if fact is None:
                reasons.append("numeric_fact_missing")
            elif fact_id not in claim_markers:
                reasons.append("numeric_fact_not_rendered")
            elif fact.source_id not in claim_source_ids:
                reasons.append("numeric_fact_source_missing")
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
    return _render(draft, evidence, source_records, availability)


_REASON_TEXT = {
    "structured_report_invalid": "The report format was invalid.",
    "evidence_unavailable": "Requested evidence was unavailable.",
    "provider_response_partial": "The provider response was incomplete.",
    "runtime_failure": "The research workflow stopped before all requested steps completed.",
    "major_claim_unsupported": "A main conclusion lacked cited evidence.",
    "numeric_claim_unbound": "A number was not linked to verified data.",
    "numeric_fact_missing": "A cited number was absent from verified data.",
    "numeric_fact_reference_missing": "A fact marker was not linked to a claim's numeric references.",
    "lookup_answer_not_claim_backed": "The lookup summary did not match a cited claim.",
    "numeric_fact_source_missing": "A cited number did not resolve to a cited source.",
    "citation_source_missing": "A citation did not match a verified source.",
    "citation_source_url_missing": "A citation source did not provide a URL.",
    "degraded_source_claim": "A citation source was degraded and cannot support a verified conclusion.",
}


def _source_records(evidence: dict[str, EvidenceFact]) -> dict[str, EvidenceFact]:
    sources: dict[str, EvidenceFact] = {}
    for fact in sorted(evidence.values(), key=lambda item: item.fact_id):
        current = sources.get(fact.source_id)
        if current is None or (
            bool(fact.source_url),
            fact.observed_at,
        ) > (
            bool(current.source_url),
            current.observed_at,
        ):
            sources[fact.source_id] = fact
    return sources


def report_validation_fallback(
    evidence: dict[str, EvidenceFact],
    reasons: tuple[str, ...] = (),
    availability: dict[str, dict[str, object]] | None = None,
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
            "## Research report\n"
            "### Executive Summary\n"
            "I could not verify a complete narrative from the available inputs."
            + explanation
            + "\n\n## Verified evidence\n"
            "No verified evidence was returned.\n\n"
            "## Data limitations\n"
            "- The requested data or provider response was unavailable.\n"
            "- No unsupported financial figure or conclusion was inferred.\n"
            "- Missing evidence is reported explicitly; rerun when the source is available.\n\n"
            "## Conclusion\n"
            "No financial conclusion can be made from the available evidence."
        )
    facts = sorted(
        evidence.values(), key=lambda fact: ("latest" not in fact.fact_id, fact.fact_id)
    )[:10]
    observations = "\n".join(
        f"- {fact.fact_id}: {_format_fact_value(fact)} "
        f"({fact.source_id}, observed {fact.observed_at.isoformat()})"
        for fact in facts
    )
    source_lines = "\n".join(
        f"- {fact.source_id}: {fact.source_url or 'URL unavailable'}"
        for fact in facts
        if fact.source_url
    )
    limitation_lines = "\n".join(
        f"- {source.replace('_', ' ').title()} {details.get('status')}: "
        f"{details.get('reason') or 'evidence unavailable'!s}"
        for source, details in (availability or {}).items()
        if details.get("status") in {"unavailable", "degraded"}
    )
    return (
        "## Research report\n"
        "### Executive Summary\n"
        "This is a partial report because some requested evidence was unavailable. "
        "It contains only deterministic provider observations returned by the providers.\n\n"
        "## Report Metadata\n"
        "- Evidence status: LIMITED\n"
        "- Coverage: verified provider observations only\n\n"
        "## Verified evidence\n"
        "I could not verify every requested claim. The available observations are "
        "listed below; unsupported conclusions are omitted."
        + explanation
        + "\n\n## Sources\n"
        + (source_lines or "- No source URLs were returned.")
        + "\n\n"
        + observations
        + "\n\n## Data limitations\n"
        + (limitation_lines + "\n" if limitation_lines else "")
        + "- Some requested data or source evidence was unavailable.\n"
        "- No unsupported investment conclusion was inferred.\n"
        "- Missing evidence and provider failures should be resolved before relying on the report."
    )


def report_repair_instruction(
    evidence: dict[str, EvidenceFact],
    reasons: tuple[str, ...],
    *,
    parse_error: str | None = None,
    unreferenced_fact_ids: tuple[str, ...] = (),
    sources: dict[str, dict[str, str]] | None = None,
    prompts: PromptRegistry | None = None,
) -> str:
    """Return one bounded correction request after a report-format failure."""
    selected_ids = set(unreferenced_fact_ids)
    facts = [
        fact
        for fact in evidence.values()
        if not selected_ids or fact.fact_id in selected_ids
    ][:80]
    fact_catalog = (
        "; ".join(f"{fact.fact_id} = {fact.value} {fact.unit}" for fact in facts)
        or "none"
    )
    source_ids = {fact.source_id for fact in facts}
    source_ids.update(sources or {})
    source_list = ", ".join(sorted(source_ids)) or "none"
    # Parser details can echo model output; keep them out of the next system message.
    detail = " A parser or validation error occurred." if parse_error else ""
    registry = prompts or PromptRegistry.bundled()
    return registry.render(
        "publication.report_repair",
        reasons=", ".join(reasons),
        parse_error_detail=detail,
        fact_catalog=fact_catalog,
        source_list=source_list,
        unreferenced_fact_ids=", ".join(unreferenced_fact_ids) or "none",
    )


def lookup_repair_instruction(
    evidence: dict[str, EvidenceFact],
    reasons: tuple[str, ...],
    *,
    sources: dict[str, dict[str, str]] | None = None,
    prompts: PromptRegistry | None = None,
) -> str:
    fact_catalog = (
        "; ".join(
            f"{fact.fact_id} = {fact.value} {fact.unit}"
            for fact in list(evidence.values())[:80]
        )
        or "none"
    )
    source_ids = {fact.source_id for fact in evidence.values()}
    source_ids.update(sources or {})
    return (prompts or PromptRegistry.bundled()).render(
        "agent_loop.lookup.repair",
        lookup_schema=json.dumps(
            LookupAnswerV1.model_json_schema(), sort_keys=True, separators=(",", ":")
        ),
        reasons=", ".join(reasons),
        fact_catalog=fact_catalog,
        source_list=", ".join(sorted(source_ids)) or "none",
    )


def _source_url(source: EvidenceFact | dict[str, str]) -> str:
    if isinstance(source, EvidenceFact):
        return source.source_url or ""
    return str(source.get("url") or "")


def _source_display(source: EvidenceFact | dict[str, str]) -> str:
    if isinstance(source, EvidenceFact):
        return f"{source.source_url} (observed {source.observed_at.isoformat()})"
    observed_at = source.get("observed_at")
    return (
        f"{_source_url(source)} (observed {observed_at})"
        if observed_at
        else _source_url(source)
    )


def _render(
    draft: ReportDraft,
    evidence: dict[str, EvidenceFact],
    source_records: dict[str, EvidenceFact | dict[str, str]] | None = None,
    availability: dict[str, dict[str, object]] | None = None,
) -> str:
    def replace(text: str) -> str:
        return _FACT_MARKER.sub(
            lambda match: _format_fact_value(evidence[match.group(1)]),
            text,
        )

    records: dict[str, EvidenceFact | dict[str, str]] = (
        source_records
        if source_records is not None
        else {key: value for key, value in _source_records(evidence).items()}
    )
    cited_source_ids = {citation.source_id for citation in draft.citations}
    limited = any(
        item.get("status") in {"unavailable", "empty", "degraded"}
        for item in (availability or {}).values()
    )
    metadata = [
        "Report title: Research report",
        f"Evidence status: {'LIMITED' if limited else 'COMPLETE'}",
    ]
    if evidence:
        metadata.append(
            "Evidence observed through: "
            f"{max(fact.observed_at for fact in evidence.values()).isoformat()}"
        )
    if any(
        "historical_prices:data.period_return_pct" == fact.fact_id
        for fact in evidence.values()
    ):
        metadata.append("Price return basis: see provider adjustment metadata")
    if not any(fact.source_id.startswith("fundamentals") for fact in evidence.values()):
        metadata.append("Coverage: technical analysis with limited company evidence")
    sections = [
        ("Report Metadata", "\n".join(f"- {item}" for item in metadata)),
        ("Executive Summary", replace(draft.executive_summary)),
        ("Key Drivers", "\n".join(f"- {replace(item)}" for item in draft.key_drivers)),
        ("Detailed Analysis", replace(draft.detailed_analysis)),
        (
            "Risks and Contrarian View",
            "\n".join(f"- {replace(item)}" for item in draft.risks),
        ),
        ("Final View", replace(draft.final_view)),
        (
            "Claims and references",
            "\n".join(
                f"- {replace(claim.text)} [citations: {', '.join(claim.evidence_refs)}]"
                for claim in draft.claims
            ),
        ),
        (
            "Sources",
            "\n".join(
                f"- {source_id}: {_source_display(fact)}"
                for source_id, fact in sorted(records.items())
                if source_id in cited_source_ids
            ),
        ),
    ]
    unavailable = [
        item
        for item in (availability or {}).values()
        if item.get("status") in {"unavailable", "degraded"}
    ]
    if unavailable:
        limitations = "\n".join(
            f"- {item.get('source')}: "
            f"{('News evidence was unavailable' if item.get('source') == 'news' else 'Evidence quality was degraded') if item.get('status') == 'degraded' else ('News evidence was unavailable' if item.get('source') == 'news' else 'Evidence was unavailable')}"
            f" ({item.get('reason') or 'unavailable'})"
            for item in unavailable
        )
        sections.append(("Evidence limitations", limitations))
    return "\n\n".join(f"## {title}\n{body}" for title, body in sections)


def _format_fact_value(fact: EvidenceFact) -> str:
    """Render provider values with metric-specific presentation semantics."""
    if fact.unit in {"provider_date", "provider_timestamp"}:
        return str(fact.value)
    if fact.unit != "provider_value":
        return f"{fact.value} {fact.unit}"
    field = fact.fact_id.rsplit(".", 1)[-1].lower()
    if field.endswith(("_pct", "percent")) or any(
        token in field for token in ("margin", "growth", "yield")
    ):
        return f"{float(fact.value):.2f}%"
    if field in {"volume", "row_count", "marketcap", "obv"}:
        return f"{float(fact.value):,.0f}"
    if isinstance(fact.value, int) or float(fact.value).is_integer():
        return f"{float(fact.value):,.0f}"
    return f"{float(fact.value):.2f}".rstrip("0").rstrip(".")
