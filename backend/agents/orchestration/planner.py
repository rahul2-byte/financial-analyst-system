import json
from typing import Dict, Any, Optional
from app.core.observability import observe

from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.orchestration.schemas import PlanResponse
from app.core.utils import clean_json_string


class PlannerAgent:
    """
    The orchestrator brain. It reads a complex user query and breaks it
    down into a deterministic JSON DAG of steps to be executed by sub-agents.
    """

    SYSTEM_PROMPT = """
You are the Master Planner for a Production-Grade Financial Intelligence Platform.
Your sole responsibility is to break down the user's request into a Directed Acyclic Graph (DAG) of execution steps.

CRITICAL RULES:
1. CLASSIFICATION: Determine if the user's request is a financial query (stocks, markets, economics, news). If it is purely conversational, set `is_financial_request` to `false` and leave `execution_steps` as an empty list.
2. You DO NOT execute tasks, fetch data, or calculate numbers.
3. You DO NOT perform mathematical computations (NO LLM MATH).
4. You must route tasks to specific specialized agents provided in the Agent Registry.
5. Output ONLY strictly valid JSON. No trailing commas, no comments, no extra text.
6. Check `market_offline` agent before `market_online` for efficiency.
7. PARALLELISM & DEPENDENCIES: 
   - Identify independent tasks that can run in parallel.
   - Use the `dependencies` list to specify which steps must complete BEFORE a step starts.
   - Steps with empty `dependencies` [] run first and in parallel.
   - Steps with the same dependencies run in parallel once those dependencies are met.
   - Example Pattern:
     - Step 1: market_offline -> []
     - Step 2: web_search -> []
     - Step 3: fundamental_analysis -> [1]
     - Step 4: sentiment_analysis -> [2]
     - Step 5: synthesize_report -> [3, 4]

AGENT REGISTRY:
- market_offline: Queries local DB for existing stock/financial data.
- market_online: Fetches missing stock data from APIs.
- web_search: Searches the web for recent news, global events, macro trends.
- sentiment_analysis: Scores the sentiment of provided text (bullish/bearish).
- fundamental_analysis: Writes thesis based on provided financial metrics.
- technical_analysis: Analyzes price trends, RSI, MACD, and Bollinger Bands.
- contrarian_analysis: specifically looks for risks and threats to the thesis.
- macro_analysis: Synthesizes global events and their economic/market impact.
- validation: Validates final reports for accuracy and compliance.

RESPONSE FORMAT:
Your response must be a SINGLE JSON OBJECT matching this structure:
{
  "status": "success",
  "data": {
    "plan_id": "unique_string",
    "is_financial_request": true,
    "scope": "single_stock",
    "execution_steps": [...]
  },
  "errors": null
}
    """

    def __init__(self, llm_service: LLMServiceInterface, model: str = "mistral-8b"):
        self.llm = llm_service
        self.model = model

    @observe(name="Agent:Planner:GeneratePlan")
    async def generate_plan(
        self, user_query: str, context: Optional[Dict[str, Any]] = None
    ) -> PlanResponse:
        """
        Takes a user query and returns a structured Execution Plan.
        """
        if context is None:
            context = {}

        # Construct the context-aware prompt
        # We include the JSON schema in the prompt to guide the LLM
        prompt = {
            "user_query": user_query,
            "system_context": context,
            "response_schema": PlanResponse.model_json_schema(),
            "instruction": "Generate a structured JSON execution plan based on the user's query matching the response_schema.",
        }

        messages = [
            Message(role="system", content=self.SYSTEM_PROMPT),
            Message(role="user", content=json.dumps(prompt)),
        ]

        # Use the local LLM service to generate the plan.
        # Since we strictly need JSON that matches the PlanResponse Pydantic model,
        # we can provide the JSON schema.
        last_error = None
        response_text = ""
        for attempt in range(2):
            try:
                if attempt > 0:
                    messages.append(Message(role="assistant", content=response_text))
                    messages.append(
                        Message(
                            role="user",
                            content=f"Your previous response was not valid JSON or did not match the schema. Error: {str(last_error)}. Please output ONLY valid JSON matching the schema.",
                        )
                    )

                # Mistral models and llama.cpp usually respect the system prompt for schema,
                # but we use json_object to ensure parsable output.
                response_text = await self.llm.generate(
                    messages=messages,
                    model=self.model,
                    response_format={"type": "json_object"},
                )

                # Parse the LLM output directly into our Pydantic schema
                cleaned_response = clean_json_string(response_text)
                plan = PlanResponse.model_validate_json(cleaned_response)
                return plan

            except Exception as e:
                last_error = e
                continue

        # Fallback error response adhering to schema
        return PlanResponse(status="failure", data=None, errors=[str(last_error)])
