import json
from typing import Optional
from app.core.observability import observe

from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.analysis.schemas import AgentResponse, MacroInsights


class MacroAnalysisAgent:
    """
    Agent responsible for analyzing broad economic trends, global events,
    and their impacts on the financial markets.
    """

    SYSTEM_PROMPT = """
You are the Senior Macro-Economic Analyst for a Financial Intelligence Platform.
Your job is to read news, global event data, and economic indicators to assess the broad market impact.

CRITICAL RULES:
1. FOCUS on macro drivers: Interest rates, inflation (CPI/WPI), GDP growth, commodity prices (Oil/Gold), and geopolitical events.
2. SYNTHESIZE how these events affect the Indian and global markets.
3. Your final output must EXACTLY match the MacroInsights JSON schema. Do not output anything outside of the JSON.
    """

    def __init__(self, llm_service: LLMServiceInterface, model: str = "mistral-8b"):
        self.llm = llm_service
        self.model = model

    @observe(name="Agent:Macro:Execute")
    async def execute(
        self, user_query: str, context_data: Optional[str] = None
    ) -> AgentResponse:
        """
        Executes the macro analysis loop.
        """
        prompt = (
            f"Analyze the macro-economic context for the following query: {user_query}"
        )
        if context_data:
            prompt += f"\n\nContextual Data provided:\n{context_data[:10000]}"

        messages = [
            Message(role="system", content=self.SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ]

        try:
            # Macro agent usually does a single direct synthesis turn based on provided context
            messages.append(
                Message(
                    role="user",
                    content=f"Synthesize your findings into a JSON object matching this schema: {json.dumps(MacroInsights.model_json_schema())}",
                )
            )

            response_msg = await self.llm.generate_message(
                messages=messages,
                model=self.model,
                response_format={"type": "json_object"},
            )

            final_content = response_msg.content

            try:
                if not final_content:
                    raise ValueError("Final content is empty")
                parsed_insights = json.loads(final_content)
            except Exception:
                # Basic parsing fallback if clean_json_string wasn't enough (unlikely with our setup)
                from app.core.utils import clean_json_string

                parsed_insights = json.loads(clean_json_string(final_content))

            return AgentResponse(status="success", data=parsed_insights, errors=None)

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
