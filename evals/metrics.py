"""Deterministic metrics for FIN-AI evaluation records."""

from __future__ import annotations

from collections.abc import Iterable
from math import log2
from typing import Any

_ABSTENTION_STATUSES = {"refused", "incomplete", "needs_review", "insufficient_data"}


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def reciprocal_rank(ranked_ids: list[str], relevant_ids: set[str]) -> float:
    for rank, item in enumerate(ranked_ids, 1):
        if item in relevant_ids:
            return 1.0 / rank
    return 0.0


def hit_rate_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    return float(bool(set(ranked_ids[:k]) & relevant_ids)) if relevant_ids else 0.0


def recall_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    return round(len(set(ranked_ids[:k]) & relevant_ids) / len(relevant_ids), 6)


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
    checked_citations = citations & required_citations
    numeric_matched, numeric_total = _numeric_provenance(task, result)
    expected_risks = _normalise_risks(task.get("required_risks", []))
    actual_risks = _normalise_risks(result.get("risks", []))
    forbidden = set(task.get("forbidden_claim_types", []))
    actual_forbidden = forbidden & set(result.get("claim_types", []))
    terminal_status = result.get("terminal_status")
    expected_status = task.get("expected_terminal_status")
    abstention_expected = expected_status in _ABSTENTION_STATUSES
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
        "abstention_expected": abstention_expected,
        "abstention_correct": abstention_expected
        and terminal_status == expected_status,
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


def _metric_count(count: int, denominator: int) -> dict[str, int]:
    return {"count": count, "denominator": denominator}


def _resolved_claim_label(
    records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if len({str(record.get("labeler_id")) for record in records}) < 2:
        return None
    adjudicated = [record for record in records if record.get("adjudicated")]
    if adjudicated:
        return adjudicated[-1]
    signatures = {
        (
            record.get("numeric_value_correct"),
            record.get("semantic_judgment"),
        )
        for record in records
    }
    return records[0] if len(signatures) == 1 else None


def _claim_failure_example(
    category: str, claim: dict[str, Any], label: dict[str, Any] | None = None
) -> dict[str, Any]:
    example = {
        "category": category,
        "claim_id": claim.get("claim_id"),
        "claim_text": claim.get("text", ""),
    }
    if label is not None:
        example.update(
            {
                "source_id": label.get("source_id"),
                "evidence_span": label.get("evidence_span"),
            }
        )
    return example


def evaluate_claim_support(
    case_id: str,
    result: dict[str, Any],
    labels: list[dict[str, Any]],
    judge_labels: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score major claims using structural references and resolved human labels."""
    claims = [
        claim
        for claim in result.get("claims", [])
        if isinstance(claim, dict) and claim.get("importance") == "major"
    ]
    citations = {
        str(citation.get("citation_id")): citation
        for citation in result.get("citations", [])
        if isinstance(citation, dict) and citation.get("citation_id")
    }
    reference_valid = 0
    failure_examples: list[dict[str, Any]] = []
    for claim in claims:
        references = claim.get("evidence_refs", [])
        valid = bool(references) and all(
            ref in citations and bool(citations[ref].get("source_id"))
            for ref in references
        )
        reference_valid += valid
        if not valid:
            failure_examples.append(_claim_failure_example("invalid_reference", claim))

    grouped: dict[str, list[dict[str, Any]]] = {}
    for label in labels:
        if str(label.get("case_id")) == case_id:
            grouped.setdefault(str(label.get("claim_id")), []).append(label)
    resolved: dict[str, dict[str, Any]] = {}
    unresolved = 0
    for claim in claims:
        claim_id = str(claim.get("claim_id"))
        records = grouped.get(claim_id, [])
        if not records:
            continue
        resolved_label = _resolved_claim_label(records)
        if resolved_label is None:
            unresolved += 1
            failure_examples.append(
                _claim_failure_example("unresolved_label_disagreement", claim)
            )
        else:
            resolved[claim_id] = resolved_label

    labeled_claims = len(resolved)
    numeric_labels = [
        label
        for claim in claims
        if claim.get("numeric_refs")
        for label in [resolved.get(str(claim.get("claim_id")))]
        if label is not None and label.get("numeric_value_correct") is not None
    ]
    numeric_correct = sum(
        label.get("numeric_value_correct") is True for label in numeric_labels
    )
    numeric_incorrect = len(numeric_labels) - numeric_correct
    for claim in claims:
        numeric_label = resolved.get(str(claim.get("claim_id")))
        if claim.get("numeric_refs") and numeric_label is not None:
            if numeric_label.get("numeric_value_correct") is False:
                failure_examples.append(
                    _claim_failure_example(
                        "incorrect_numeric_value", claim, numeric_label
                    )
                )
            elif numeric_label.get("numeric_value_correct") is None:
                continue
    semantic_labels = list(resolved.items())
    supports = sum(
        label.get("semantic_judgment") == "supports" for _, label in semantic_labels
    )
    contradictory = sum(
        label.get("semantic_judgment") == "contradicts" for _, label in semantic_labels
    )
    unsupported = sum(
        label.get("semantic_judgment") == "unsupported" for _, label in semantic_labels
    )
    for claim in claims:
        semantic_label = resolved.get(str(claim.get("claim_id")))
        if semantic_label is not None and semantic_label.get("semantic_judgment") in {
            "contradicts",
            "unsupported",
        }:
            failure_examples.append(
                _claim_failure_example(
                    str(semantic_label["semantic_judgment"]), claim, semantic_label
                )
            )

    judge_comparison = _compare_judge_labels(
        resolved, judge_labels or [], case_id, claims
    )
    return {
        "status": "human_labels_available" if resolved else "insufficient_evidence",
        "major_claims": _metric_count(len(claims), len(claims)),
        "labeled_claims": _metric_count(labeled_claims, len(claims)),
        "valid_reference": _metric_count(reference_valid, len(claims)),
        "numeric_value_correct": _metric_count(numeric_correct, len(numeric_labels)),
        "numeric_value_incorrect": _metric_count(
            numeric_incorrect, len(numeric_labels)
        ),
        "source_supports_claim": _metric_count(supports, labeled_claims),
        "contradictory_source_evidence": _metric_count(contradictory, labeled_claims),
        "unsupported_conclusion": _metric_count(unsupported, labeled_claims),
        "unresolved_label_disagreement": _metric_count(unresolved, len(claims)),
        "failure_examples": failure_examples,
        "judge_comparison": judge_comparison,
    }


def _compare_judge_labels(
    resolved: dict[str, dict[str, Any]],
    judge_labels: list[dict[str, Any]],
    case_id: str,
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    if not judge_labels:
        return {
            "status": "not_evaluated",
            "semantic_disagreement": _metric_count(0, 0),
            "numeric_disagreement": _metric_count(0, 0),
            "examples": [],
        }
    by_claim = {
        str(label.get("claim_id")): label
        for label in judge_labels
        if str(label.get("case_id")) == case_id
    }
    semantic_denominator = 0
    numeric_denominator = 0
    semantic_disagreement = 0
    numeric_disagreement = 0
    examples: list[dict[str, Any]] = []
    claim_map = {str(claim.get("claim_id")): claim for claim in claims}
    for claim_id, human in resolved.items():
        judge = by_claim.get(claim_id)
        if judge is None:
            continue
        if human.get("semantic_judgment") in {
            "supports",
            "contradicts",
            "unsupported",
        } and judge.get("semantic_judgment") in {
            "supports",
            "contradicts",
            "unsupported",
        }:
            semantic_denominator += 1
            if human["semantic_judgment"] != judge["semantic_judgment"]:
                semantic_disagreement += 1
                examples.append(
                    _claim_failure_example(
                        "judge_semantic_disagreement", claim_map[claim_id]
                    )
                )
        if (
            human.get("numeric_value_correct") is not None
            and judge.get("numeric_value_correct") is not None
        ):
            numeric_denominator += 1
            if human["numeric_value_correct"] != judge["numeric_value_correct"]:
                numeric_disagreement += 1
                examples.append(
                    _claim_failure_example(
                        "judge_numeric_disagreement", claim_map[claim_id]
                    )
                )
    return {
        "status": "recorded_judge_available",
        "semantic_disagreement": _metric_count(
            semantic_disagreement, semantic_denominator
        ),
        "numeric_disagreement": _metric_count(
            numeric_disagreement, numeric_denominator
        ),
        "examples": examples,
    }


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def _aggregate_claim_support(
    claim_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    fields = (
        "major_claims",
        "labeled_claims",
        "valid_reference",
        "numeric_value_correct",
        "numeric_value_incorrect",
        "source_supports_claim",
        "contradictory_source_evidence",
        "unsupported_conclusion",
        "unresolved_label_disagreement",
    )
    totals = {
        field: _metric_count(
            sum(int(item.get(field, {}).get("count", 0)) for item in claim_metrics),
            sum(
                int(item.get(field, {}).get("denominator", 0)) for item in claim_metrics
            ),
        )
        for field in fields
    }
    failures = [
        example
        for item in claim_metrics
        for example in item.get("failure_examples", [])
    ][:50]
    judge_items = [
        item.get("judge_comparison", {})
        for item in claim_metrics
        if item.get("judge_comparison", {}).get("status") == "recorded_judge_available"
    ]
    if judge_items:
        judge = {
            "status": "recorded_judge_available",
            "semantic_disagreement": _metric_count(
                sum(item["semantic_disagreement"]["count"] for item in judge_items),
                sum(
                    item["semantic_disagreement"]["denominator"] for item in judge_items
                ),
            ),
            "numeric_disagreement": _metric_count(
                sum(item["numeric_disagreement"]["count"] for item in judge_items),
                sum(
                    item["numeric_disagreement"]["denominator"] for item in judge_items
                ),
            ),
            "examples": [
                example for item in judge_items for example in item.get("examples", [])
            ][:50],
        }
    else:
        judge = {
            "status": "not_evaluated",
            "semantic_disagreement": _metric_count(0, 0),
            "numeric_disagreement": _metric_count(0, 0),
            "examples": [],
        }
    return {
        "status": (
            "human_labels_available"
            if any(
                item.get("status") == "human_labels_available" for item in claim_metrics
            )
            else "insufficient_evidence"
        ),
        **totals,
        "failure_examples": failures,
        "judge_comparison": judge,
    }


def aggregate_metrics(
    case_metrics: list[dict[str, Any]],
    claim_support_metrics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate per-case results; empty input is explicitly insufficient."""
    count = len(case_metrics)
    numeric = [float(item["numeric_provenance_rate"]) for item in case_metrics]
    evidence = [item.get("evidence_selection", {}) for item in case_metrics]
    abstention_cases = [
        item for item in case_metrics if item.get("abstention_expected", False)
    ]
    return {
        "case_count": count,
        "status": "case_metrics_available" if count else "insufficient_evidence",
        "task_completion_rate": _rate(
            sum(bool(item.get("task_completed")) for item in case_metrics), count
        ),
        "abstention_case_count": len(abstention_cases),
        "abstention_accuracy": _rate(
            sum(bool(item.get("abstention_correct")) for item in abstention_cases),
            len(abstention_cases),
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
            "hit_rate_at_5": _mean(
                [float(item.get("hit_rate_at_5", 0.0)) for item in evidence]
            ),
            "hit_rate_at_10": _mean(
                [float(item.get("hit_rate_at_10", 0.0)) for item in evidence]
            ),
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
        "human_claim_support": _aggregate_claim_support(claim_support_metrics or []),
    }
