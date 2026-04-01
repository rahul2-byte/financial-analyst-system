from __future__ import annotations

from typing import Any
import json

from app.core.graph.router_policy import decide_next_action


async def autonomous_router_node(state: dict[str, Any]) -> dict[str, Any]:
    next_iteration = int(state.get("iteration_count", 0)) + 1
    decision = decide_next_action(state)
    terminal_output: dict[str, Any] | None = None
    if decision.startswith("terminate_") and not state.get("final_output"):
        terminal_status = "insufficient_data" if decision == "terminate_insufficient_data" else "failure"
        if decision == "terminate_success":
            terminal_status = "success"
        terminal_output = {
            "status": terminal_status,
            "decision": "no_call" if terminal_status != "success" else "watchlist",
            "confidence_score": float(state.get("confidence_score", 0.0)),
            "final_confidence": float(state.get("final_confidence", state.get("confidence_score", 0.0))),
            "key_drivers": [],
            "risks": ["insufficient validated evidence"],
            "data_used": state.get("data_status", {}),
            "insufficiency_markers": ["INSUFFICIENT_DATA"],
            "reasoning": f"Terminated via router decision '{decision}'.",
            "next_action": "complete",
        }
    return {
        "iteration_count": next_iteration,
        "router_decision": decision,
        "termination_reason": decision if decision.startswith("terminate_") else None,
        "status": "success",
        "reasoning": f"Router selected '{decision}' on iteration {next_iteration}.",
        "confidence_score": float(state.get("confidence_score", 0.0)),
        "next_action": decision,
        "data": {"router_decision": decision},
        "errors": [],
        "history": [{"node": "router", "decision": decision, "iteration": next_iteration}],
        "final_output": terminal_output,
        "final_report": json.dumps(terminal_output, ensure_ascii=True)
        if terminal_output is not None
        else None,
    }
