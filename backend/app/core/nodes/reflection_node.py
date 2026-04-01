from __future__ import annotations

from typing import Any


async def reflection_node(state: dict[str, Any]) -> dict[str, Any]:
    retry_count_by_domain = dict(state.get("retry_count_by_domain", {}))
    retry_count_by_domain["research"] = retry_count_by_domain.get("research", 0) + 1

    return {
        "status": "success",
        "reasoning": "Identified weak evidence/confidence and requested targeted replan.",
        "confidence_score": float(state.get("confidence_score", 0.0)),
        "next_action": "run_research_plan",
        "data": {
            "reflection": {
                "root_cause": "low_evidence_or_conflict",
                "improvements": ["increase high-signal tasks", "refresh stale datasets"],
            }
        },
        "results": {
            "reflection": {
                "root_cause": "low_evidence_or_conflict",
                "improvements": ["increase high-signal tasks", "refresh stale datasets"],
            }
        },
        "retry_count_by_domain": retry_count_by_domain,
        "errors": [],
    }
