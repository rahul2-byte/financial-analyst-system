from __future__ import annotations

import json
from typing import Any

from app.config import settings
from app.core.contracts.graph_node import finalize_node_output
from app.core.intelligence import (
    EvaluationFeedback,
    IntelligenceAction,
    SystemIntelligenceLayer,
)
from app.core.node_resources import resources
from app.core.orchestration_schemas import EvaluatorResult
from app.core.policies.json_parse_policy import parse_json_from_llm_response
from app.core.prompts import prompt_manager
from app.models.request_models import Message
from app.config.constants import MODEL_REASONING


def _fallback_evaluation(state: dict[str, Any], reason: str) -> EvaluatorResult:
    final_output = state.get("final_output", {})
    if not isinstance(final_output, dict):
        return EvaluatorResult(
            score=0.0,
            error_type="formatting_error",
            feedback="Final output is missing or malformed.",
        )

    if final_output.get("insufficiency_markers"):
        return EvaluatorResult(
            score=max(0.0, min(0.55, float(final_output.get("confidence_score", 0.0)))),
            error_type="incomplete_response",
            feedback="Output remains incomplete because insufficiency markers are present.",
        )

    if state.get("hallucination_issues"):
        return EvaluatorResult(
            score=0.2,
            error_type="hallucination",
            feedback="Critic reported unsupported claims that must be corrected.",
        )

    if state.get("critic_decision") == "conflict":
        return EvaluatorResult(
            score=0.35,
            error_type="reasoning_error",
            feedback="Critic detected unresolved conflicts in the synthesized thesis.",
        )

    if not state.get("validation_passed", False):
        return EvaluatorResult(
            score=0.1,
            error_type="formatting_error",
            feedback="Validation did not pass, so the output contract is not reliable.",
        )

    return EvaluatorResult(
        score=min(0.45, max(0.0, float(final_output.get("confidence_score", 0.0)))),
        error_type="reasoning_error",
        feedback=f"Evaluator fallback triggered because the evaluator response was unavailable or invalid: {reason}",
    )


def _reprioritize_tasks(
    tasks: list[dict[str, Any]],
    error_type: str,
    correction_prompt: str | None,
) -> list[dict[str, Any]]:
    replanned: list[dict[str, Any]] = []
    for task in tasks:
        updated = dict(task)
        if updated.get("priority") in {"P1", "P2"}:
            updated["priority"] = "P0"
        params = dict(updated.get("parameters", {}))
        if correction_prompt:
            params["correction_prompt"] = correction_prompt
        if error_type in {"hallucination", "factual_error", "reasoning_error"}:
            params["verification_focus"] = error_type
        updated["parameters"] = params
        replanned.append(updated)
    return replanned


def _memory_store():
    existing = getattr(resources, "_sql_db", None)
    if existing is not None:
        return existing
    try:
        return resources.sql_db
    except Exception:  # noqa: BLE001
        return None


async def evaluator_node(state: dict[str, Any]) -> dict[str, Any]:
    final_output = state.get("final_output", {})
    final_output_json = json.dumps(final_output, ensure_ascii=True, default=str)
    system_prompt = prompt_manager.get_prompt("evaluator.system")
    user_prompt = prompt_manager.get_prompt(
        "evaluator.user",
        user_query=state.get("user_query", ""),
        final_output_json=final_output_json,
        critic_decision=state.get("critic_decision", "none"),
        validation_passed=state.get("validation_passed", False),
    )

    evaluation: EvaluatorResult | None = None
    errors: list[str] = []

    try:
        response = await resources.llm_service.generate_message(
            messages=[
                Message(role="system", content=system_prompt),
                Message(role="user", content=user_prompt),
            ],
            model=MODEL_REASONING,
        )
        parsed = parse_json_from_llm_response(getattr(response, "content", None))
        if isinstance(parsed, dict):
            evaluation = EvaluatorResult.model_validate(parsed)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"evaluator_llm_error: {exc}")

    if evaluation is None:
        evaluation = _fallback_evaluation(
            state, errors[0] if errors else "invalid_evaluator_payload"
        )

    sil = SystemIntelligenceLayer(
        memory_store=_memory_store(),
        max_retries=3,
        pass_threshold=0.8,
    )
    decision = sil.process_evaluation(
        query_id=str(
            state.get("query_id")
            or state.get("goal", {}).get("ticker")
            or state.get("user_query", "unknown")
        ),
        user_input=str(state.get("user_query", "")),
        candidate_output=final_output_json,
        evaluation=EvaluationFeedback(
            score=float(evaluation.score),
            error_type=evaluation.error_type.value,
            feedback=evaluation.feedback,
        ),
        current_retries=int(state.get("retry_count_by_domain", {}).get("research", 0)),
        agent_name="evaluator",
    )

    evaluation_payload = {
        "score": decision.normalized_score,
        "error_type": decision.error_type,
        "feedback": decision.feedback,
    }
    retry_counts = dict(state.get("retry_count_by_domain", {}))
    retry_counts["research"] = decision.retry_count
    payload: dict[str, Any] = {
        "evaluation_result": evaluation_payload,
        "evaluation_passed": decision.action == IntelligenceAction.TERMINATE_SUCCESS,
        "retry_count_by_domain": retry_counts,
        "intelligence_decision": sil.as_payload(decision),
        "status": "success",
        "reasoning": "Evaluated final output quality and applied system intelligence routing.",
        "confidence_score": decision.normalized_score,
        "data": {
            "evaluation": evaluation_payload,
            "intelligence_decision": sil.as_payload(decision),
        },
        "errors": errors,
    }

    if decision.action == IntelligenceAction.TERMINATE_SUCCESS:
        payload["next_action"] = "run_router"
        return finalize_node_output("evaluator_node", payload)

    if decision.action == IntelligenceAction.RETRY:
        payload.update(
            {
                "next_action": "run_router",
                "force_replan": True,
                "tasks": [],
                "replanned_tasks": _reprioritize_tasks(
                    list(state.get("tasks", [])),
                    decision.error_type,
                    decision.correction_prompt,
                ),
                "correction_prompt": decision.correction_prompt,
                "validation_passed": False,
                "evaluation_passed": False,
                "final_output": None,
                "final_report": None,
            }
        )
        return finalize_node_output("evaluator_node", payload)

    terminal_output = {
        "status": "failure",
        "decision": "no_call",
        "confidence_score": decision.normalized_score,
        "final_confidence": decision.normalized_score,
        "key_drivers": [],
        "risks": [decision.feedback],
        "data_used": state.get("data_status", {}),
        "insufficiency_markers": [decision.error_type],
        "reasoning": "System intelligence exhausted retry budget after evaluation failure.",
        "next_action": "complete",
    }
    payload.update(
        {
            "next_action": "terminate_failure",
            "final_output": terminal_output,
            "final_report": json.dumps(terminal_output, ensure_ascii=True),
        }
    )
    return finalize_node_output("evaluator_node", payload)
