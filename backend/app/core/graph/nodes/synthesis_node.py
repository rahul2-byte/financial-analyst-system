"""Synthesis graph node handler."""

import logging
from typing import Any, Dict

from app.config import settings
from app.core.graph.graph_state import ResearchGraphState
from app.core.node_resources import NodeResources
from app.core.prompts import prompt_manager
from app.models.request_models import Message

logger = logging.getLogger(__name__)


async def synthesis_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Generates draft report from agent outputs using LLM."""
    user_query = state["user_query"]
    agent_outputs = state.get("agent_outputs", {})
    synthesis_retry_count = state.get("synthesis_retry_count", 0)
    verification_feedback = state.get("verification_feedback", "")

    logger.info(
        f"Synthesis node generating draft report (attempt {synthesis_retry_count + 1})"
    )

    try:
        conflict_record = state.get("conflict_record")
        conflict_instructions = ""
        if conflict_record:
            conflict_instructions = """
            CRITICAL: A persistent conflict was detected between agents. 
            You MUST present BOTH perspectives fairly. 
            Use a 'Dueling Perspectives' or 'Conflicting Signals' section to explain the disagreement.
            """

        prompt_header = prompt_manager.get_prompt(
            "orchestrator.synthesis.header", user_query=user_query
        )
        agent_output_sections = [
            f"{prompt_manager.get_prompt('orchestrator.synthesis.section_header', section_name=f'Step {step_num}')}\n{output}"
            for step_num, output in agent_outputs.items()
        ]
        prompt = prompt_header + "\n\n" + conflict_instructions + "\n\n" + "\n\n".join(agent_output_sections)

        if verification_feedback:
            prompt += "\n\n" + prompt_manager.get_prompt(
                "orchestrator.synthesis.feedback", error=verification_feedback
            )

        prompt += prompt_manager.get_prompt("orchestrator.synthesis.instructions")

        response = await resources.llm_service.generate_message(
            messages=[Message(role="user", content=prompt)],
            model=settings.DEFAULT_LLM_MODEL,
        )
        draft_report = response.content or ""

        if not draft_report:
            return {
                "errors": ["Synthesis failed to generate draft report"],
                "synthesis_retry_count": synthesis_retry_count + 1,
                "failed_node": "synthesis_node"
            }

        return {
            "draft_report": draft_report,
            "synthesis_retry_count": synthesis_retry_count + 1,
        }

    except Exception as error:
        logger.error(f"Synthesis node error: {error}", exc_info=True)
        return {
            "errors": [f"Synthesis error: {str(error)}"],
            "synthesis_retry_count": synthesis_retry_count + 1,
            "failed_node": "synthesis_node"
        }
