import json
from typing import Dict, Any, Optional

from app.core.observability import observe
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.analysis.schemas import AgentResponse


class ContrarianAgent:
    """
    Agent responsible for finding reasons to reject an investment thesis.
    It acts as a professional skeptic, analyzing data for risks, weaknesses, and threats.
    """

    SYSTEM_PROMPT = """
You are the Contrarian ('Bear Case') Agent for a Financial Intelligence Platform.
Your sole mission is to find reasons to REJECT an investment thesis. You are the professional skeptic.
Your job is to read provided news, sentiment, and fundamental data, and identify every possible risk, regulatory threat, competitive weakness, and negative trend.

CRITICAL RULES:
1. Focus strictly on the Bear Case. Do not balance it with positives.
2. Look for 'Tail Risks' (low probability, high impact events).
3. Identify contradictions in news reports or management claims.
4. Your final response should be a bulleted 'Risk Assessment' report.
5. Always respond with JSON matching the AgentResponse schema.
    """

    def __init__(self, llm_service: LLMServiceInterface, model: str = "mistral-8b"):
        self.llm = llm_service
        self.model = model

    @observe(name="Agent:Contrarian:Execute")
    async def execute(
        self, user_query: str, context_data: Optional[Dict[str, Any]] = None
    ) -> AgentResponse:
        """
        Executes the agent loop.
        Processes news, sentiment, and fundamental data to identify risks.
        """
        prompt = user_query
        if context_data:
            prompt += f"\n\nHere is the context data (news, sentiment, fundamentals) you must analyze for risks: {json.dumps(context_data)}"

        messages = [
            Message(role="system", content=self.SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ]

        try:
            response_msg = await self.llm.generate_message(
                messages=messages, model=self.model
            )

            content = response_msg.content

            # Attempt to parse as AgentResponse JSON if the LLM followed instructions strictly
            try:
                parsed_json = json.loads(content)
                if (
                    isinstance(parsed_json, dict)
                    and "status" in parsed_json
                    and "data" in parsed_json
                ):
                    return AgentResponse(**parsed_json)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

            # Fallback: Wrap the response content in the AgentResponse schema
            # Use 'response' key for consistency with the PipelineOrchestrator
            return AgentResponse(
                status="success", data={"response": content}, errors=None
            )

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
