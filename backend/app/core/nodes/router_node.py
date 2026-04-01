from __future__ import annotations

from typing import Any

from app.core.router_policy import decide_next_action


async def router_node(state: dict[str, Any]) -> dict[str, Any]:
    decision = decide_next_action(state)
    return {
        "status": "success",
        "router_decision": decision,
        "reasoning": f"Router selected next action '{decision}' based on deterministic policy.",
        "confidence_score": float(state.get("confidence_score", 0.0)),
        "next_action": decision,
        "data": {"router_decision": decision},
        "errors": [],
    }
