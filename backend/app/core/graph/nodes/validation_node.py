"""Stateless validation node - validates draft report for compliance."""

import json
import logging
from typing import Dict, Any

from pydantic import BaseModel, Field

from app.core.node_resources import NodeResources


class ValidationResult(BaseModel):
    """Structured validation response from LLM."""

    is_compliant: bool = Field(
        description="Whether the report passes compliance checks"
    )
    violations: list[str] = Field(
        default_factory=list, description="List of compliance violations found"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-critical warnings"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in the validation decision"
    )


from app.core.prompts import prompt_manager
from app.models.request_models import Message
from quant.validators import ReportValidator
from app.config import settings

logger = logging.getLogger(__name__)


async def validation_node(
    state: Dict[str, Any], resources: NodeResources
) -> Dict[str, Any]:
    """
    Stateless validation node - validates draft report for compliance.

    Uses deterministic ReportValidator for fast checks and LLM for compliance.
    """
    llm_service = resources.llm_service
    model = settings.DEFAULT_LLM_MODEL

    user_query = state.get("user_query", "")
    draft_report = state.get("draft_report", "")

    logger.info("Validation node checking compliance")

    check_results = {}
    processed_text = draft_report

    try:
        # First, run deterministic checks
        validator = ReportValidator()
        check_results = validator.run_checks(draft_report)

        if check_results.get("is_critical_failure"):
            return {
                "final_report": None,
                "errors": check_results.get("violations", []),
                "failed_node": "validation_node"
            }

        # Use processed text (with disclaimer if added)
        processed_text = check_results.get("processed_text", draft_report)

        # Now use LLM for final compliance check
        messages = [
            Message(
                role="system", content=prompt_manager.get_prompt("validation.system")
            ),
            Message(
                role="user",
                content=prompt_manager.get_prompt(
                    "validation.user",
                    user_query=user_query,
                    draft_report=processed_text,
                ),
            ),
        ]

        # Use LLM tool calling for structured validation
        validation_schema = ValidationResult.model_json_schema()

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "submit_validation_result",
                    "description": "Submit the validation result for the draft report",
                    "parameters": validation_schema,
                },
            }
        ]

        response = await llm_service.generate_message(
            messages=messages, model=model, tools=tools
        )

        # Parse structured response
        validation_result = None
        if response.tool_calls:
            for tool_call in response.tool_calls:
                func = tool_call.get("function", {})
                if func.get("name") == "submit_validation_result":
                    args_str = func.get("arguments", "{}")
                    args = (
                        json.loads(args_str) if isinstance(args_str, str) else args_str
                    )
                    validation_result = ValidationResult.model_validate(args)

        # If we got structured result, use it
        if validation_result:
            if validation_result.is_compliant:
                logger.info(
                    f"Validation passed (confidence: {validation_result.confidence})"
                )
                
                # Persist to audit log before clearing state
                resources.sql_db.log_research_action(
                    query_id=state.get("user_query", "unknown"),
                    agent_name="ValidationAgent",
                    action="REPORT_APPROVED",
                    data={"confidence": validation_result.confidence}
                )

                return {
                    "final_report": processed_text,
                    "agent_outputs": {}, # State Cleanup
                    "status": "completed"
                }
            else:
                logger.warning(f"Validation failed: {validation_result.violations}")
                return {
                    "final_report": None,
                    "errors": validation_result.violations,
                }

        # Fallback: if tool calling failed, use simple heuristic
        logger.warning("Structured validation failed, falling back to heuristic")
        if not check_results.get("has_violations"):
            return {"final_report": processed_text}

        return {
            "final_report": None,
            "errors": check_results.get("violations", []),
        }

    except Exception as e:
        logger.error(f"Validation node error: {e}", exc_info=True)
        # On error, fall back to deterministic checks only
        if not check_results.get("has_violations"):
            return {"final_report": processed_text}
        return {
            "final_report": None,
            "errors": [f"Validation error: {str(e)}"],
            "failed_node": "validation_node"
        }
