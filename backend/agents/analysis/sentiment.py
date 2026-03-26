import json
from typing import Dict, Any, Optional, List

from app.core.observability import observe
from app.core.prompts import prompt_manager
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.analysis.schemas import AgentResponse
from quant.nlp_scorer import NLPScorer
from agents.base import BaseAgent


class SentimentAnalysisAgent(BaseAgent):
    """
    Hybrid Agent combining deterministic FinBERT scoring (via Python)
    with LLM-based reasoning to extract actionable insights from unstructured text.
    """

    def __init__(self, llm_service: LLMServiceInterface, model: str = "mistral-8b"):
        super().__init__(llm_service, model)
        self.scorer = NLPScorer()

    def _get_tools(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_finbert_analysis",
                    "description": "Runs deterministic FinBERT sentiment scoring on raw text.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "The raw unstructured text to analyze.",
                            }
                        },
                        "required": ["text"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_sentiment_analysis",
                    "description": "Submits the final qualitative sentiment analysis.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "finbert_overall_score": {"type": "string"},
                            "finbert_guidance_score": {"type": "string"},
                            "order_book_updates": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "major_challenges": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "entity_impact_map": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "entity_name": {"type": "string"},
                                        "relationship": {"type": "string"},
                                        "impact": {"type": "string"},
                                    },
                                    "required": [
                                        "entity_name",
                                        "relationship",
                                        "impact",
                                    ],
                                },
                            },
                            "is_contradictory": {"type": "boolean"},
                            "contradiction_reason": {"type": "string"},
                            "executive_summary": {"type": "string"},
                        },
                        "required": [
                            "finbert_overall_score",
                            "finbert_guidance_score",
                            "is_contradictory",
                            "executive_summary",
                        ],
                    },
                },
            },
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Executes the requested tool."""
        try:
            if tool_name == "run_finbert_analysis":
                text = arguments.get("text", "")
                if not text:
                    return json.dumps({"error": "No text provided"})
                results = self.scorer.analyze_text(text)
                return json.dumps(results)
            elif tool_name == "submit_sentiment_analysis":
                return json.dumps(arguments)
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:Sentiment:Execute")
    async def execute(
        self, user_query: str, step_number: int = 0, raw_text_data: Optional[str] = None
    ) -> AgentResponse:
        """
        Executes the agent loop with flexible multi-turn tool usage.
        """
        max_turns = 5
        prompt = user_query
        if raw_text_data:
            prompt += f"\n\nHere is the raw text you must analyze:\n{raw_text_data}"

        messages: List[Message] = [
            Message(
                role="system", content=prompt_manager.get_prompt("sentiment.system")
            ),
            Message(role="user", content=prompt),
        ]

        try:
            for turn in range(max_turns):
                response_msg = await self.llm_service.generate_message(
                    messages=messages, model=self.model, tools=self._get_tools()
                )
                messages.append(response_msg)

                if not response_msg.tool_calls:
                    return AgentResponse(
                        status="failure",
                        data={},
                        errors=["Agent did not call any tools."],
                    )

                # Execute all tool calls in this turn
                for tool_call in response_msg.tool_calls:
                    function_call = tool_call.get("function", {})
                    tool_name = function_call.get("name")

                    # Parse arguments safely
                    arguments_str = function_call.get("arguments", "{}")
                    try:
                        arguments = (
                            json.loads(arguments_str)
                            if isinstance(arguments_str, str)
                            else arguments_str
                        )
                    except json.JSONDecodeError:
                        arguments = {}

                    # If it's the final submission tool, we're done
                    if tool_name == "submit_sentiment_analysis":
                        final_data = self._execute_tool(tool_name, arguments)
                        return AgentResponse(
                            status="success", data=json.loads(final_data), errors=None
                        )

                    # Otherwise, execute the tool and add result to context
                    tid = await self.emit_status(
                        step_number,
                        tool_name,
                        "Running sentiment analysis...",
                        status="running",
                    )
                    tool_result = self._execute_tool(tool_name, arguments)
                    await self.emit_status(
                        step_number,
                        tool_name,
                        "Running sentiment analysis...",
                        "Done.",
                        status="completed",
                        tool_id=tid,
                    )

                    messages.append(
                        Message(
                            role="tool",
                            content=tool_result,
                            name=tool_name,
                            tool_call_id=tool_call.get("id"),
                        )
                    )

            # If we hit max turns without submission
            return AgentResponse(
                status="failure",
                data={},
                errors=[
                    f"Agent failed to submit sentiment analysis within {max_turns} turns."
                ],
            )

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
