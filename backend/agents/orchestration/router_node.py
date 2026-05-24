from __future__ import annotations

from typing import Any
import json

from app.core.contracts.graph_node import finalize_node_output
from app.core.graph.router_policy import (
    CRITIC_RETRY_LIMIT,
    RESEARCH_PLAN_LOOP_LIMIT,
    decide_next_action,
    build_router_decision_snapshot,
)
from app.core.audit import build_node_audit_entry
from app.core.node_resources import resources
from app.core.observability import observe, opik_context
from app.core.report_renderer import generate_narrative_report


def _build_router_audit(
    state: dict[str, Any], payload: dict[str, Any], decision: str, next_iteration: int
) -> dict[str, Any]:
    audit = build_node_audit_entry("router_node", state, payload)
    retry_counts = state.get("retry_count_by_domain", {})
    if isinstance(retry_counts, dict):
        retry_summary = {
            str(key): int(value) if isinstance(value, int) else value
            for key, value in retry_counts.items()
        }
    else:
        retry_summary = {}

    decision_reason_hint = "default"
    if decision == "run_research_plan" and bool(state.get("force_replan", False)):
        decision_reason_hint = "force_replan"
    elif decision == "terminate_low_confidence":
        decision_reason_hint = "low_confidence_guard"
    elif decision == "terminate_insufficient_data":
        decision_reason_hint = "insufficient_data"
    elif decision == "run_data_fetch":
        decision_reason_hint = "materialization_missing"

    snapshot = build_router_decision_snapshot(state)
    audit["decision_summary"] = {
        "router_decision": decision,
        "iteration": next_iteration,
        "has_goal": bool(state.get("goal")),
        "has_tasks": bool(state.get("tasks")),
        "has_results": bool(state.get("results")),
        "force_replan": bool(state.get("force_replan", False)),
        "retry_count_by_domain": retry_summary,
        "decision_reason_hint": decision_reason_hint,
        "router_snapshot": snapshot,
    }
    return audit


def _low_confidence_reason(state: dict[str, Any]) -> str:
    critic_retries = int(state.get("retry_count_by_domain", {}).get("critic", 0))
    if state.get("critic_decision") == "retry" and critic_retries >= CRITIC_RETRY_LIMIT:
        return (
            "Evidence remained too weak after repeated critic review, so the system "
            "stopped additional replanning and published the best available report "
            "with low confidence."
        )

    repeated_replans = int(state.get("consecutive_research_plan_routes", 0))
    if repeated_replans >= RESEARCH_PLAN_LOOP_LIMIT:
        return (
            "The system detected repeated research replanning without enough forward "
            "progress, so it stopped the loop and published the best available report "
            "with low confidence."
        )

    return (
        "The system stopped additional replanning and published the best available "
        "report with low confidence."
    )


def _build_low_confidence_output(state: dict[str, Any]) -> dict[str, Any]:
    existing = state.get("final_output")
    if not isinstance(existing, dict):
        existing = {}

    synthesis = state.get("results", {}).get("synthesis", {})
    if not isinstance(synthesis, dict):
        synthesis = {}

    confidence_score = float(
        existing.get("confidence_score", state.get("confidence_score", 0.0))
    )
    final_confidence = float(existing.get("final_confidence", confidence_score))

    return {
        "status": "low_confidence",
        "decision": existing.get("decision") or synthesis.get("decision", "no_call"),
        "confidence_score": confidence_score,
        "final_confidence": final_confidence,
        "key_drivers": existing.get("key_drivers") or synthesis.get("key_drivers", []),
        "risks": existing.get("risks") or synthesis.get("risks", []),
        "data_used": state.get("data_status", {}),
        "insufficiency_markers": existing.get("insufficiency_markers")
        or synthesis.get("insufficiency_markers", []),
        "reasoning": _low_confidence_reason(state),
        "next_action": "complete",
    }


@observe(name="Research:Router", as_type="span")
async def router_node(state: dict[str, Any]) -> dict[str, Any]:
    next_iteration = int(state.get("iteration_count", 0)) + 1
    decision = decide_next_action(state)

    opik_context.update_current_span(
        metadata={
            "router_decision": decision,
            "iteration": next_iteration,
            "force_replan": bool(state.get("force_replan", False)),
        }
    )

    consecutive_research_plan_routes = (
        int(state.get("consecutive_research_plan_routes", 0)) + 1
        if decision == "run_research_plan"
        else 0
    )
    terminal_output: Any | None = None
    final_report = state.get("final_report")
    if decision == "terminate_low_confidence":
        terminal_output = _build_low_confidence_output(state)
        final_report = await generate_narrative_report(
            state,
            resources,
            terminal_output=terminal_output,
            is_low_confidence=True,
            reason=terminal_output.get("reasoning"),
        )
    elif decision.startswith("terminate_") and not state.get("final_output"):
        terminal_status = (
            "insufficient_data"
            if decision == "terminate_insufficient_data"
            else "failure"
        )
        if decision == "terminate_success":
            terminal_status = "success"
        if decision == "terminate_awaiting_input":
            prompt_text = (
                state.get("plan", {}).get("assistant_response")
                if isinstance(state.get("plan"), dict)
                else None
            )
            prompt_text_final = (
                prompt_text
                if isinstance(prompt_text, str) and prompt_text.strip()
                else "Please provide clarification or approve the proposed plan."
            )
            terminal_output = {
                "status": "awaiting_user_input",
                "decision": "awaiting_input",
                "confidence_score": float(state.get("confidence_score", 0.0)),
                "final_confidence": float(
                    state.get("final_confidence", state.get("confidence_score", 0.0))
                ),
                "key_drivers": [],
                "risks": [],
                "data_used": state.get("data_status", {}),
                "insufficiency_markers": [],
                "reasoning": prompt_text_final,
                "next_action": "await_user_input",
            }
            final_report = prompt_text_final
        else:
            terminal_output = {
                "status": terminal_status,
                "decision": "no_call" if terminal_status != "success" else "watchlist",
                "confidence_score": float(state.get("confidence_score", 0.0)),
                "final_confidence": float(
                    state.get("final_confidence", state.get("confidence_score", 0.0))
                ),
                "key_drivers": [],
                "risks": ["insufficient validated evidence"],
                "data_used": state.get("data_status", {}),
                "insufficiency_markers": ["INSUFFICIENT_DATA"],
                "reasoning": f"Terminated via router decision '{decision}'.",
                "next_action": "complete",
            }
            final_report = json.dumps(terminal_output, ensure_ascii=True)
    if not decision.startswith("terminate_"):
        payload = {
            "iteration_count": next_iteration,
            "router_decision": decision,
            "status": "success",
            "reasoning": f"Router selected '{decision}' on iteration {next_iteration}.",
            "confidence_score": float(state.get("confidence_score", 0.0)),
            "next_action": decision,
            "data": {"router_decision": decision},
            "errors": [],
            "history": [
                {"node": "router", "decision": decision, "iteration": next_iteration}
            ],
            "consecutive_research_plan_routes": consecutive_research_plan_routes,
            "final_output": state.get("final_output"),
            "final_report": state.get("final_report"),
        }
        payload["data"]["audit"] = _build_router_audit(
            state, payload, decision, next_iteration
        )
        return finalize_node_output("router_node", payload)

    payload = {
        "iteration_count": next_iteration,
        "router_decision": decision,
        "termination_reason": decision,
        "status": "success",
        "reasoning": f"Router selected '{decision}' on iteration {next_iteration}.",
        "confidence_score": float(state.get("confidence_score", 0.0)),
        "next_action": decision,
        "data": {"router_decision": decision},
        "errors": [],
        "history": [
            {"node": "router", "decision": decision, "iteration": next_iteration}
        ],
        "consecutive_research_plan_routes": consecutive_research_plan_routes,
        "final_output": (
            terminal_output
            if terminal_output is not None
            else state.get("final_output")
        ),
        "final_report": final_report,
    }
    payload["data"]["audit"] = _build_router_audit(
        state, payload, decision, next_iteration
    )
    return finalize_node_output("router_node", payload)
