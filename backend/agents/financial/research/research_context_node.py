"""Research context assembly node."""

from __future__ import annotations

from typing import Any

from agents.financial.research.context_assembly import build_execution_input
from app.core.audit import build_node_audit_entry
from app.core.contracts.graph_node import finalize_node_output
from app.core.research_plan_schemas import ResearchTaskSpec


async def research_context_node(state: dict[str, Any]) -> dict[str, Any]:
    task_contexts: dict[str, Any] = {}
    errors: list[str] = []

    fetched_data = dict(state.get("fetched_data", {}))
    data_status = dict(state.get("data_status", {}))

    for raw_task in state.get("tasks", []):
        try:
            task = ResearchTaskSpec.model_validate(raw_task)
            execution_input = build_execution_input(task, fetched_data, data_status)
            task_contexts[task.task_id] = execution_input.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            task_id = (
                raw_task.get("task_id", "unknown_task")
                if isinstance(raw_task, dict)
                else "unknown_task"
            )
            errors.append(f"{task_id}: context_assembly_failed: {exc}")

    status = "success"
    if errors and task_contexts:
        status = "partial"
    elif errors:
        status = "failure"

    payload = {
        "task_contexts": task_contexts,
        "status": status,
        "reasoning": "Built agent-specific research execution context.",
        "confidence_score": float(state.get("confidence_score", 0.6)),
        "next_action": (
            "run_research_execution" if status != "failure" else "terminate_failure"
        ),
        "data": {"task_context_count": len(task_contexts)},
        "errors": errors,
    }

    audit = build_node_audit_entry("research_context_node", state, payload)

    retrieval_diagnostics = {}
    for task_id, context_json in task_contexts.items():
        bundle = context_json.get("evidence_bundle", {})
        retrieval = bundle.get("retrieval", {})
        warnings = bundle.get("warnings", [])

        retrieval_diagnostics[task_id] = {
            "returned_count": retrieval.get("returned_count", 0),
            "failure_reason": retrieval.get("failure_reason"),
            "fallback_used": "used_fetched_news_fallback" in warnings,
        }

    audit["decision_summary"] = {
        "agents_configured": list(task_contexts.keys()),
        "task_context_count": len(task_contexts),
        "context_assembly_errors": errors[:10],
        "retrieval_diagnostics": retrieval_diagnostics,
    }
    payload["data"]["audit"] = audit

    return finalize_node_output("research_context_node", payload)
