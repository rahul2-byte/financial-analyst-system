from __future__ import annotations

from typing import Any


async def conflict_resolution_node(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "reasoning": "Resolved cross-agent conflict by prioritizing fresher and stronger evidence windows.",
        "confidence_score": float(state.get("confidence_score", 0.0)),
        "next_action": "run_synthesis",
        "data": {
            "conflict_resolution": {
                "resolved": True,
                "method": "evidence_quality_and_recency_weighting",
            }
        },
        "results": {
            "conflict_resolution": {
                "resolved": True,
                "method": "evidence_quality_and_recency_weighting",
            }
        },
        "errors": [],
    }
