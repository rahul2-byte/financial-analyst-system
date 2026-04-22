"""Sentiment analysis graph node handler."""

import json
from typing import Any, Dict

from app.core.graph.graph_state import ResearchGraphState
from app.core.graph.node_helpers import build_node_error, build_node_success
from app.core.node_resources import NodeResources
from app.models.request_models import Message
from app.core.research_plan_schemas import AgentExecutionInput
from app.core.prompts import prompt_manager
from app.config.constants import MODEL_REASONING
from app.core.research_schemas import ResearchAgentResult
from agents.financial.analysis.payload_sanitizer import (
    drop_findings_without_evidence_ids,
)


async def sentiment_analysis_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Uses LLM to analyze pre-fetched sentiment evidence."""
    current_step = state.get("current_step") or {}
    params = current_step.get("parameters", {})
    if not isinstance(params, dict):
        params = {}

    execution_input = None
    if isinstance(params.get("execution_input"), dict):
        execution_input = AgentExecutionInput.model_validate(params["execution_input"])

    evidence_text = ""
    if execution_input is not None:
        evidence_text = "\n\n---\n\n".join(
            [
                f"Source: {item.source} ({item.published_date})\nContent: {item.text}"
                for item in execution_input.evidence_bundle.qualitative_inputs
            ]
        )
    else:
        evidence_text = params.get("text", "") or params.get("raw_data") or ""

    try:
        if not evidence_text:
            agent_result = ResearchAgentResult(
                agent="sentiment_analysis",
                status="insufficient_evidence",
                findings=[],
                claims=[],
                missing_evidence=["Sentiment evidence text is missing"],
                confidence=0.0,
            )

            agent_result.audit = {
                "node": "sentiment_analysis",
                "ticker": (
                    params.get("ticker", "UNKNOWN")
                    if execution_input is None
                    else execution_input.ticker
                ),
                "status": agent_result.status,
                "confidence": agent_result.confidence,
                "findings_count": len(agent_result.findings),
                "claims_count": len(agent_result.claims),
                "missing_evidence_count": len(agent_result.missing_evidence),
            }

            return build_node_success(
                agent_output_key="sentiment_analysis",
                agent_output=agent_result.model_dump(mode="json"),
                tool_name="analysis:sentiment_analysis_result",
                input_parameters=params,
                tool_output=agent_result.model_dump(mode="json"),
            )

        system_prompt = prompt_manager.get_prompt("sentiment.system")
        user_prompt = prompt_manager.get_prompt(
            "sentiment.user_node",
            text=(
                evidence_text
                if isinstance(evidence_text, str)
                else json.dumps(evidence_text)
            ),
        )
        if execution_input is not None:
            user_prompt += (
                f"\n\nResearch objective: {execution_input.objective}"
                f"\nResearch question: {execution_input.research_question}"
            )

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
                {"agent": "sentiment_analysis", **raw_payload}
            )
        except Exception:
            # Fallback for parsing errors
            agent_result = ResearchAgentResult(
                agent="sentiment_analysis",
                status="failed",
                findings=[],
                claims=[],
                missing_evidence=[
                    "Failed to parse LLM response into ResearchAgentResult"
                ],
                confidence=0.0,
            )

        agent_result.audit = {
            "node": "sentiment_analysis",
            "ticker": (
                params.get("ticker", "UNKNOWN")
                if execution_input is None
                else execution_input.ticker
            ),
            "status": agent_result.status,
            "confidence": agent_result.confidence,
            "findings_count": len(agent_result.findings),
            "claims_count": len(agent_result.claims),
            "missing_evidence_count": len(agent_result.missing_evidence),
        }

        return build_node_success(
            agent_output_key="sentiment_analysis",
            agent_output=agent_result.model_dump(mode="json"),
            tool_name="analysis:sentiment_analysis_result",
            input_parameters=params,
            tool_output=agent_result.model_dump(mode="json"),
        )
    except Exception as error:
        return build_node_error(error)
