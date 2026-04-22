"""Technical analysis graph node handler."""

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


async def technical_analysis_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Uses LLM to analyze pre-fetched technical data."""
    current_step = state.get("current_step") or {}
    params = current_step.get("parameters", {})
    if not isinstance(params, dict):
        params = {}

    execution_input = None
    if isinstance(params.get("execution_input"), dict):
        execution_input = AgentExecutionInput.model_validate(params["execution_input"])

    import pandas as pd
    from quant.indicators import TechnicalScanner

    ticker = (
        execution_input.ticker
        if execution_input is not None and execution_input.ticker
        else params.get("ticker", "UNKNOWN")
    )
    raw_data = (
        execution_input.evidence_bundle.structured_inputs.get("ohlcv", {})
        if execution_input is not None
        else params.get("raw_data") or state.get("fetched_data", {}).get("ohlcv", {})
    )

    try:
        if not raw_data:
            # (Keep existing insufficient evidence logic)
            pass

        # NARRATOR REFACTOR: Convert to DataFrame and get compressed signals
        # We NO LONGER pass raw_data to the LLM.

        # Robust record extraction: raw_data is often {"ticker": "...", "data": [...]}
        records = []
        if isinstance(raw_data, dict):
            records = raw_data.get("data", []) if "data" in raw_data else [raw_data]
        elif isinstance(raw_data, list):
            records = raw_data

        df = pd.DataFrame(records)

        if df.empty or len(df) < 30:
            signals = {
                "error": f"Insufficient candle data ({len(df)} rows) for technical narrative."
            }
        else:
            signals = TechnicalScanner.get_signal_summary(df)

        system_prompt = prompt_manager.get_prompt("technical.system")
        user_prompt = prompt_manager.get_prompt(
            "technical.user_node",
            ticker=ticker,
            signals=json.dumps(signals),  # Compressed JSON summary only
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
                {"agent": "technical_analysis", **raw_payload}
            )
        except Exception:
            # Fallback for parsing errors
            agent_result = ResearchAgentResult(
                agent="technical_analysis",
                status="failed",
                findings=[],
                claims=[],
                missing_evidence=[
                    "Failed to parse LLM response into ResearchAgentResult"
                ],
                confidence=0.0,
            )

        agent_result.audit = {
            "node": "technical_analysis",
            "ticker": ticker,
            "status": agent_result.status,
            "confidence": agent_result.confidence,
            "findings_count": len(agent_result.findings),
            "claims_count": len(agent_result.claims),
            "missing_evidence_count": len(agent_result.missing_evidence),
        }

        return build_node_success(
            agent_output_key="technical_analysis",
            agent_output=agent_result.model_dump(mode="json"),
            tool_name="analysis:technical_analysis_result",
            input_parameters=params,
            tool_output=agent_result.model_dump(mode="json"),
        )
    except Exception as error:
        return build_node_error(error)
