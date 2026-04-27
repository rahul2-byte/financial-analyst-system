from __future__ import annotations

from app.core.research_plan_schemas import QualitativeEvidenceItem


def format_qualitative_evidence(item: QualitativeEvidenceItem) -> str:
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    evidence_id = item.evidence_id or metadata.get("evidence_id") or "unknown"
    url = metadata.get("url") or metadata.get("canonical_url") or ""
    return (
        f"[evidence_id: {evidence_id}] Source: {item.source} "
        f"Date: {item.published_date} URL: {url}\nContent: {item.text}"
    )
