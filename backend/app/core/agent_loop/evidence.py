"""Run-scoped accounting for evidence returned by tools."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

from app.core.agent_loop.publication import EvidenceFact
from app.core.research_schemas import EvidenceProvenance

_EVIDENCE_TOOLS = {
    "data:fetch_stock_data",
    "data:fetch_fundamentals",
    "news:fetch_news",
    "analysis:run_fundamental_scan",
    "analysis:run_technical_scan",
    "analysis:get_technical_overview",
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
        self.availability: dict[str, dict[str, Any]] = {}
        self.sources: dict[str, dict[str, str]] = {}

    def record_success(self, name: str, payload: dict[str, Any]) -> None:
        if name not in _EVIDENCE_TOOLS:
            return
        self.successful_evidence_tools += 1
        extracted = extract_evidence_facts(payload)
        self.facts.update(extracted)
        source = _source_name(name)
        source_records = payload.get("sources")
        if isinstance(source_records, list):
            for record in source_records:
                if isinstance(record, dict) and record.get("url"):
                    source_id = str(record.get("name") or source)
                    self.sources[source_id] = {
                        "name": source_id,
                        "url": str(record["url"]),
                    }
        provenance = payload.get("provenance")
        if isinstance(provenance, dict) and provenance.get("source"):
            source_id = str(provenance["source"])
            self.sources.setdefault(
                source_id,
                {
                    "name": source_id,
                    "url": str(provenance.get("source_url") or ""),
                    "quality_status": str(provenance.get("quality_status") or ""),
                    "observed_at": str(provenance.get("observed_at") or ""),
                },
            )
        valid = name not in _PROVENANCE_REQUIRED_TOOLS or valid_provenance(payload)
        quality_status = (
            str(provenance.get("quality_status"))
            if isinstance(provenance, dict)
            else ""
        )
        self.availability[source] = {
            "source": source,
            "status": (
                "unavailable"
                if not valid
                else "degraded"
                if quality_status == "degraded"
                else "available"
            ),
            "reason": (
                "invalid provenance"
                if not valid
                else "provider quality degraded"
                if quality_status == "degraded"
                else None
            ),
            "evidence_count": len(extracted),
        }
        if not valid:
            self.invalid_evidence = True

    def record_failure(self, name: str, payload: dict[str, Any]) -> None:
        if name in _EVIDENCE_TOOLS and not payload.get("retryable", False):
            self.failed_evidence_tools += 1
            source = _source_name(name)
            self.availability[source] = {
                "source": source,
                "status": "unavailable",
                "reason": str(payload.get("error") or "tool failed"),
                "evidence_count": 0,
            }


def _source_name(name: str) -> str:
    return {
        "news:fetch_news": "news",
        "data:fetch_stock_data": "market_data",
        "data:fetch_fundamentals": "fundamentals",
        "analysis:run_fundamental_scan": "fundamental_analysis",
        "analysis:run_technical_scan": "technical_analysis",
        "analysis:get_technical_overview": "technical_overview",
    }.get(name, name)


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

    def safe_path(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_.:-]+", "_", value).strip("_") or "field"

    def visit(value: Any, path: str) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            if isinstance(value, float) and not math.isfinite(value):
                return
            fact_id = f"{source_id}:{safe_path(path)}"
            facts[fact_id] = EvidenceFact(
                fact_id=fact_id,
                value=value,
                unit="provider_value",
                source_id=source_id,
                instrument=instrument,
                observed_at=observed,
                quality_status="verified",
                source_url=str(provenance.get("source_url") or "") or None,
            )
        elif isinstance(value, str):
            try:
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    date.fromisoformat(value)
                    unit = "provider_date"
                elif re.match(r"^\d{4}-\d{2}-\d{2}[T ]", value):
                    datetime.fromisoformat(value)
                    unit = "provider_timestamp"
                else:
                    return
            except ValueError:
                return
            fact_id = f"{source_id}:{safe_path(path)}"
            facts[fact_id] = EvidenceFact(
                fact_id=fact_id,
                value=value,
                unit=unit,
                source_id=source_id,
                instrument=instrument,
                observed_at=observed,
                quality_status="verified",
                source_url=str(provenance.get("source_url") or "") or None,
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
