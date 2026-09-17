"""Run-scoped accounting for evidence returned by tools."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from app.core.agent_loop.publication import EvidenceFact
from app.core.research_schemas import EvidenceProvenance

_EVIDENCE_TOOLS = {
    "data:fetch_stock_data",
    "data:fetch_fundamentals",
    "news:fetch_news",
    "analysis:run_fundamental_scan",
    "analysis:run_technical_scan",
}
_PROVENANCE_REQUIRED_TOOLS = {
    "data:fetch_stock_data",
    "data:fetch_fundamentals",
    "news:fetch_news",
}


class EvidenceAccounting:
    """Track only validated evidence that may support publication."""

    def __init__(self) -> None:
        self.successful_evidence_tools = 0
        self.failed_evidence_tools = 0
        self.invalid_evidence = False
        self.facts: dict[str, EvidenceFact] = {}

    def record_success(self, name: str, payload: dict[str, Any]) -> None:
        if name not in _EVIDENCE_TOOLS:
            return
        self.successful_evidence_tools += 1
        self.facts.update(extract_evidence_facts(payload))
        if name in _PROVENANCE_REQUIRED_TOOLS and not valid_provenance(payload):
            self.invalid_evidence = True

    def record_failure(self, name: str, payload: dict[str, Any]) -> None:
        if name in _EVIDENCE_TOOLS and not payload.get("retryable", False):
            self.failed_evidence_tools += 1


def extract_evidence_facts(payload: dict[str, Any]) -> dict[str, EvidenceFact]:
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        return {}
    source_id = str(provenance.get("dataset") or provenance.get("source") or "")
    instrument = str(provenance.get("instrument") or "")
    if (
        not source_id
        or not instrument
        or provenance.get("quality_status") != "verified"
    ):
        return {}
    try:
        observed = datetime.fromisoformat(str(provenance.get("observed_at")))
        datetime.fromisoformat(str(provenance.get("ingested_at")))
    except (TypeError, ValueError):
        return {}
    facts: dict[str, EvidenceFact] = {}

    def visit(value: Any, path: str) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            if isinstance(value, float) and not math.isfinite(value):
                return
            fact_id = f"{source_id}:{path}"
            facts[fact_id] = EvidenceFact(
                fact_id=fact_id,
                value=value,
                unit="provider_value",
                source_id=source_id,
                instrument=instrument,
                observed_at=observed,
                quality_status="verified",
            )
        elif isinstance(value, dict):
            for key, item in value.items():
                visit(item, f"{path}.{key}" if path else str(key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}.{index}")

    visit(payload.get("data"), "data")
    return facts


def valid_provenance(payload: dict[str, Any]) -> bool:
    raw = payload.get("provenance")
    if not isinstance(raw, dict):
        return False
    try:
        provenance = EvidenceProvenance.model_validate(raw)
    except Exception:  # noqa: BLE001 - malformed provider metadata is evidence failure
        return False
    return (
        provenance.quality_status != "rejected"
        and provenance.ingested_at >= provenance.observed_at
    )
