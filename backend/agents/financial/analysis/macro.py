"""Macro analysis graph node handler."""

import json
from typing import Any

from agents.financial.analysis.payload_sanitizer import (
    drop_findings_without_evidence_ids,
)
from agents.shared.contracts import ResearchState
from agents.shared.node_helpers import build_node_error, build_node_success
from app.config.constants import MODEL_REASONING
from app.core.node_resources import NodeResources
from app.core.observability import observe, run_context
from app.core.prompts import prompt_manager
from app.core.research_plan_schemas import AgentExecutionInput
from app.core.research_schemas import ResearchAgentResult
from app.models.request_models import Message


@observe(name="Agent:Macro", as_type="span")
async def macro_analysis_node(
    state: ResearchState, resources: NodeResources
) -> dict[str, Any]:
    """Analyzes macroeconomic trends using pre-fetched data."""
    current_step = state.get("current_step") or {}
    params = current_step.get("parameters", {})
    if not isinstance(params, dict):
        params = {}

    execution_input = None
    if isinstance(params.get("execution_input"), dict):
        execution_input = AgentExecutionInput.model_validate(params["execution_input"])

    ticker = (
        execution_input.ticker
        if execution_input is not None and execution_input.ticker
        else params.get("ticker", "UNKNOWN")
    )
    raw_data = (
        execution_input.evidence_bundle.structured_inputs.get("macro", {})
        if execution_input is not None
        else params.get("macro_data")
        or params.get("raw_data")
        or state.get("fetched_data", {}).get("macro", {})
    )

    try:
        if not raw_data:
            agent_result = ResearchAgentResult(
                agent="macro_analysis",
                status="insufficient_evidence",
                findings=[],
                claims=[],
                missing_evidence=["Raw macro-economic data is missing"],
                confidence=0.0,
            )

            agent_result.audit = {
                "node": "macro_analysis",
                "ticker": ticker,
                "status": agent_result.status,
                "confidence": agent_result.confidence,
                "findings_count": len(agent_result.findings),
                "claims_count": len(agent_result.claims),
                "missing_evidence_count": len(agent_result.missing_evidence),
            }

            return build_node_success(
                agent_output_key="macro_analysis",
                agent_output=agent_result.model_dump(mode="json"),
                tool_name="analysis:macro_analysis_result",
                input_parameters=params,
                tool_output=agent_result.model_dump(mode="json"),
            )

        system_prompt = prompt_manager.get_prompt("macro.system")
        user_prompt = prompt_manager.get_prompt(
            "macro.user_node", ticker=ticker, data=json.dumps(raw_data, indent=2)
        )
        if execution_input is not None:
            user_prompt += (
                f"\n\nResearch objective: {execution_input.objective}"
                f"\nResearch question: {execution_input.research_question}"
            )

        if params.get("correction_prompt"):
            user_prompt += f"\n\nCORRECTION GUIDANCE:\n{params['correction_prompt']}"

        response = await resources.llm_service.generate_message(
            messages=[
                Message(role="system", content=system_prompt),
                Message(role="user", content=user_prompt),
            ],
            model=MODEL_REASONING,
            response_format={"type": "json_object"},
        )

        # Parse the structured JSON response
        try:
            raw_payload = (
                json.loads(response.content)
                if isinstance(response.content, str)
                else response.content
            )
            raw_payload = drop_findings_without_evidence_ids(raw_payload)
            # Validate against schema
            agent_result = ResearchAgentResult.model_validate(
                {"agent": "macro_analysis", **raw_payload}
            )
        except Exception:  # noqa: BLE001 - malformed model output uses fallback
            # Fallback for parsing errors
            agent_result = ResearchAgentResult(
                agent="macro_analysis",
                status="failed",
                findings=[],
                claims=[],
                missing_evidence=[
                    "Failed to parse LLM response into ResearchAgentResult"
                ],
                confidence=0.0,
            )

        agent_result.audit = {
            "node": "macro_analysis",
            "ticker": ticker,
            "status": agent_result.status,
            "confidence": agent_result.confidence,
            "findings_count": len(agent_result.findings),
            "claims_count": len(agent_result.claims),
            "missing_evidence_count": len(agent_result.missing_evidence),
        }

        run_context.update_current_span(
            metadata={
                "claims_generated": len(agent_result.claims),
                "findings_generated": len(agent_result.findings),
            }
        )

        return build_node_success(
            agent_output_key="macro_analysis",
            agent_output=agent_result.model_dump(mode="json"),
            tool_name="analysis:macro_analysis_result",
            input_parameters=params,
            tool_output=agent_result.model_dump(mode="json"),
        )
    except Exception as error:  # noqa: BLE001 - fail closed at agent boundary
        return build_node_error(error)
