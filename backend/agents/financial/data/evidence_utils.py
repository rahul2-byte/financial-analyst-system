from __future__ import annotations

from typing import Any


def as_dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def empty_dataset_evidence(ticker: str | None = None) -> dict[str, Any]:
    evidence: dict[str, Any] = {"has_data": False}
    if ticker:
        evidence["ticker"] = ticker
    return evidence


def missing_dataset_evidence(
    reason: str,
    ticker: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    evidence = empty_dataset_evidence(ticker)
    evidence["error"] = reason
    evidence.update(extra)
    return evidence


def normalize_dataset_evidence(
    payload: Any,
    *,
    ticker: str | None = None,
    default_error: str = "LOCAL_DATA_MISSING",
) -> dict[str, Any]:
    evidence = as_dict_or_empty(payload)
    if evidence.get("has_data"):
        return evidence
    return missing_dataset_evidence(
        str(evidence.get("error") or default_error),
        ticker,
        **evidence,
    )
