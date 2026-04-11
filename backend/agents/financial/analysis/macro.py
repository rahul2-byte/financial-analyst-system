"""Macro analysis graph node handler."""

import json
from typing import Any, Dict

from app.config import settings
from app.core.graph.graph_state import ResearchGraphState
from app.core.graph.node_helpers import build_node_error, build_node_success
from app.core.node_resources import NodeResources
from app.core.prompts import prompt_manager
from app.models.request_models import Message
from app.config.constants import MODEL_REASONING


async def macro_analysis_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Analyzes macroeconomic trends."""
    current_step = state.get("current_step") or {}
    params = current_step.get("parameters", {})
    if not isinstance(params, dict):
        params = {}
    macro_data = params.get("macro_data", {})
    try:
        prompt = prompt_manager.get_prompt(
            "macro.user_node",
            macro_data_json=json.dumps(macro_data),
        )
        if params.get("correction_prompt"):
            prompt += f"\n\nCORRECTION GUIDANCE:\n{params['correction_prompt']}"
        response = await resources.llm_service.generate_message(
            messages=[Message(role="user", content=prompt)],
            model=MODEL_REASONING,
        )
        result = {"macro_data": macro_data, "analysis": response.content}
        return build_node_success(
            agent_output_key="macro_analysis",
            agent_output=result,
            tool_name="analysis:analyze_macro",
            input_parameters=params,
            tool_output=result,
        )
    except Exception as error:
        return build_node_error(error)
