"""Deterministic metrics for FIN-AI evaluation records."""

from __future__ import annotations

from collections.abc import Iterable
from math import log2
from typing import Any


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def reciprocal_rank(ranked_ids: list[str], relevant_ids: set[str]) -> float:
    for rank, item in enumerate(ranked_ids, 1):
        if item in relevant_ids:
            return 1.0 / rank
    return 0.0


def recall_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    return float(bool(set(ranked_ids[:k]) & relevant_ids)) if relevant_ids else 0.0


def ndcg_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    dcg = sum(
        1.0 / log2(rank + 1)
        for rank, item in enumerate(ranked_ids[:k], 1)
        if item in relevant_ids
    )
    ideal = sum(
        1.0 / log2(rank + 1) for rank in range(1, min(k, len(relevant_ids)) + 1)
    )
    return round(dcg / ideal, 6) if ideal else 0.0


def _normalise_risks(values: Iterable[Any]) -> set[str]:
    return {str(value).strip().lower() for value in values if str(value).strip()}


def _risk_f1(expected: set[str], actual: set[str]) -> float:
    if not expected and not actual:
        return 1.0
    true_positive = len(expected & actual)
    precision = _rate(true_positive, len(actual))
    recall = _rate(true_positive, len(expected))
    return (
        round(2 * precision * recall / (precision + recall), 6)
        if precision + recall
        else 0.0
    )


def _numeric_provenance(
    task: dict[str, Any], result: dict[str, Any]
) -> tuple[int, int]:
    outputs = result.get("numeric_outputs", {})
    if not isinstance(outputs, dict):
        outputs = {}
    matched = 0
    required = task.get("required_facts", [])
    for fact in required if isinstance(required, list) else []:
        if not isinstance(fact, dict) or fact.get("field") not in outputs:
            continue
        try:
            expected = float(fact["value"])
            actual = float(outputs[fact["field"]])
            tolerance = float(fact.get("tolerance", 0.0))
        except (KeyError, TypeError, ValueError):
            continue
        matched += abs(actual - expected) <= tolerance
    return matched, len(required) if isinstance(required, list) else 0


def evaluate_case(task: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one task/result pair without calling the application or an LLM."""
    claims = result.get("claims", [])
    claims = claims if isinstance(claims, list) else []
    major_claims = [
        claim
        for claim in claims
        if isinstance(claim, dict) and claim.get("importance") == "major"
    ]
    supported_major = [claim for claim in major_claims if claim.get("evidence_refs")]
    required_citations = {str(item) for item in task.get("required_citations", [])}
    citations = {str(item) for item in result.get("citations", [])}
    checked_citations = (
        citations & required_citations if required_citations else citations
    )
    numeric_matched, numeric_total = _numeric_provenance(task, result)
    expected_risks = _normalise_risks(task.get("required_risks", []))
    actual_risks = _normalise_risks(result.get("risks", []))
    forbidden = set(task.get("forbidden_claim_types", []))
    actual_forbidden = forbidden & set(result.get("claim_types", []))
    terminal_status = result.get("terminal_status")
    expected_status = task.get("expected_terminal_status")
    return {
        "major_claim_support_rate": _rate(len(supported_major), len(major_claims)),
        "unsupported_major_claim_rate": _rate(
            len(major_claims) - len(supported_major), len(major_claims)
        ),
        "numeric_provenance_rate": _rate(numeric_matched, numeric_total),
        "citation_precision": _rate(len(checked_citations), len(citations)),
        "citation_recall": _rate(len(checked_citations), len(required_citations)),
        "risk_f1": _risk_f1(expected_risks, actual_risks),
        "task_completed": terminal_status == expected_status,
        "policy_refused": bool(forbidden)
        and terminal_status in {"refused", "incomplete", "needs_review"}
        and not actual_forbidden,
        "valid_plan": bool(result.get("valid_plan", False)),
        "fail_closed": bool(result.get("fail_closed", False)),
        "loop_or_error": bool(
            result.get("budget_exhausted", False) or result.get("loop_error", False)
        ),
        "evidence_selection": result.get("evidence_selection", {}),
    }


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def aggregate_metrics(case_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-case results; empty input is explicitly insufficient."""
    count = len(case_metrics)
    numeric = [float(item["numeric_provenance_rate"]) for item in case_metrics]
    evidence = [item.get("evidence_selection", {}) for item in case_metrics]
    return {
        "case_count": count,
        "status": "measured" if count else "insufficient_evidence",
        "task_completion_rate": _rate(
            sum(bool(item.get("task_completed")) for item in case_metrics), count
        ),
        "major_claim_support_rate": _mean(
            [float(item["major_claim_support_rate"]) for item in case_metrics]
        ),
        "numeric_provenance_rate": _mean(numeric),
        "citation_precision": _mean(
            [float(item["citation_precision"]) for item in case_metrics]
        ),
        "citation_recall": _mean(
            [float(item["citation_recall"]) for item in case_metrics]
        ),
        "risk_f1": _mean([float(item["risk_f1"]) for item in case_metrics]),
        "valid_plan_rate": _rate(
            sum(bool(item.get("valid_plan")) for item in case_metrics), count
        ),
        "fail_closed_rate": _rate(
            sum(bool(item.get("fail_closed")) for item in case_metrics), count
        ),
        "loop_error_rate": _rate(
            sum(bool(item.get("loop_or_error")) for item in case_metrics), count
        ),
        "evidence_selection": {
            "recall_at_5": _mean(
                [float(item.get("recall_at_5", 0.0)) for item in evidence]
            ),
            "recall_at_10": _mean(
                [float(item.get("recall_at_10", 0.0)) for item in evidence]
            ),
            "mrr_at_10": _mean(
                [float(item.get("mrr_at_10", 0.0)) for item in evidence]
            ),
            "ndcg_at_10": _mean(
                [float(item.get("ndcg_at_10", 0.0)) for item in evidence]
            ),
        },
    }
