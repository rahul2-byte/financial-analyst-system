from __future__ import annotations

from typing import Any


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def moving_average(values: list[float], window: int = 3) -> float:
    sample = values[-window:]
    return mean(sample)


def signal_from_text(value: Any) -> str:
    text = str(value).lower()
    if any(token in text for token in ("strong buy", "buy", "bullish", "positive")):
        return "bullish"
    if any(token in text for token in ("strong sell", "sell", "bearish", "negative")):
        return "bearish"
    return "neutral"


def horizon_from_text(value: Any) -> str:
    text = str(value).lower()
    if any(token in text for token in ("short-term", "short term", "intraday", "swing")):
        return "short"
    if any(token in text for token in ("long-term", "long term", "multi-year", "structural")):
        return "long"
    if any(token in text for token in ("mid-term", "mid term", "quarterly")):
        return "medium"
    return "unknown"


def intensity_from_text(value: Any) -> int:
    text = str(value).lower()
    if any(token in text for token in ("strong buy", "very bullish", "aggressive buy")):
        return 2
    if any(token in text for token in ("buy", "bullish", "positive")):
        return 1
    if any(token in text for token in ("strong sell", "very bearish", "aggressive sell")):
        return -2
    if any(token in text for token in ("sell", "bearish", "negative")):
        return -1
    return 0


def agent_from_tool_name(tool_name: str) -> str | None:
    lowered = tool_name.lower()
    if "fundamental" in lowered:
        return "fundamental_analysis"
    if "sentiment" in lowered or "news" in lowered:
        return "sentiment_analysis"
    if "macro" in lowered:
        return "macro_analysis"
    return None


def evidence_count_by_agent(tool_registry: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "fundamental_analysis": 0,
        "sentiment_analysis": 0,
        "macro_analysis": 0,
    }
    for entry in tool_registry:
        if not isinstance(entry, dict):
            continue
        agent = agent_from_tool_name(str(entry.get("tool_name", "")))
        if not agent:
            continue
        metrics = entry.get("extracted_metrics", {})
        if isinstance(metrics, dict):
            counts[agent] += sum(
                1 for value in metrics.values() if isinstance(value, (int, float))
            )
    return counts


def build_contradiction_records(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for i in range(len(claims)):
        for j in range(i + 1, len(claims)):
            left = claims[i]
            right = claims[j]
            left_dir = left.get("direction")
            right_dir = right.get("direction")
            if left_dir == "neutral" or right_dir == "neutral":
                continue
            if left_dir == right_dir:
                continue

            left_ev = int(left.get("evidence_count", 0))
            right_ev = int(right.get("evidence_count", 0))
            contradiction_type = "directional"
            if left_ev == 0 or right_ev == 0:
                contradiction_type = "evidence_gap"
                severity = 0.25
            else:
                left_horizon = left.get("horizon")
                right_horizon = right.get("horizon")
                if (
                    left_horizon != "unknown"
                    and right_horizon != "unknown"
                    and left_horizon != right_horizon
                ):
                    contradiction_type = "time_horizon"

                evidence_factor = min(left_ev, right_ev) / max(1, max(left_ev, right_ev))
                severity = min(0.9, 0.45 + 0.35 * evidence_factor)

            records.append(
                {
                    "type": contradiction_type,
                    "agents": [left.get("agent"), right.get("agent")],
                    "severity": round(float(severity), 4),
                    "left": left,
                    "right": right,
                }
            )
    return records


def top_metric_drivers(tool_registry: list[dict[str, Any]], limit: int = 3) -> list[str]:
    metric_pairs: list[tuple[str, float]] = []
    for entry in tool_registry:
        metrics = entry.get("extracted_metrics", {}) if isinstance(entry, dict) else {}
        if not isinstance(metrics, dict):
            continue
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                metric_pairs.append((str(key), float(value)))

    metric_pairs.sort(key=lambda item: abs(item[1]), reverse=True)
    unique: list[str] = []
    for key, _value in metric_pairs:
        if key in unique:
            continue
        unique.append(key)
        if len(unique) >= limit:
            break

    return [f"metric:{name}" for name in unique]


def evidence_ref_set(tool_registry: list[dict[str, Any]]) -> set[str]:
    refs: set[str] = set()
    for entry in tool_registry:
        if not isinstance(entry, dict):
            continue
        tool_name = str(entry.get("tool_name", ""))
        metrics = entry.get("extracted_metrics", {})
        if not tool_name or not isinstance(metrics, dict):
            continue
        for metric_name, metric_value in metrics.items():
            if isinstance(metric_value, (int, float)):
                refs.add(f"{tool_name}:{metric_name}")
    return refs


def validate_claim_evidence_links(
    claims: list[dict[str, Any]], evidence_refs: set[str]
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for claim in claims:
        claim_id = str(claim.get("claim_id", "unknown"))
        refs = claim.get("evidence_refs", [])
        if not isinstance(refs, list) or not refs:
            issues.append(
                {
                    "claim_id": claim_id,
                    "issue": "missing_evidence_refs",
                    "missing_refs": [],
                }
            )
            continue
        missing = [ref for ref in refs if str(ref) not in evidence_refs]
        if missing:
            issues.append(
                {
                    "claim_id": claim_id,
                    "issue": "invalid_evidence_refs",
                    "missing_refs": missing,
                }
            )
    return issues


def evidence_strength_from_outputs(
    results: dict[str, Any], tool_registry: list[dict[str, Any]]
) -> float:
    supported_agents = ["fundamental_analysis", "sentiment_analysis", "macro_analysis"]
    non_empty_outputs = sum(1 for agent in supported_agents if results.get(agent))
    output_coverage = non_empty_outputs / len(supported_agents)

    metric_count = 0
    for entry in tool_registry:
        metrics = entry.get("extracted_metrics", {}) if isinstance(entry, dict) else {}
        if isinstance(metrics, dict):
            metric_count += sum(
                1 for value in metrics.values() if isinstance(value, (int, float))
            )

    metrics_score = min(1.0, metric_count / 12.0)
    evidence_strength = (0.65 * output_coverage) + (0.35 * metrics_score)
    return max(0.0, min(1.0, evidence_strength))
