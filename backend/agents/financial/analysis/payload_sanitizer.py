"""Normalization helpers for analysis-node LLM payloads."""

from __future__ import annotations

from typing import Any


def drop_findings_without_evidence_ids(raw_payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(raw_payload)
    findings = sanitized.get("findings", [])
    if not isinstance(findings, list):
        sanitized["findings"] = []
        return sanitized

    sanitized["findings"] = [
        finding
        for finding in findings
        if isinstance(finding, dict)
        and isinstance(finding.get("evidence_ids"), list)
        and len(finding["evidence_ids"]) > 0
    ]
    return sanitized
