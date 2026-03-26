import json
from typing import Dict, Any, Optional, List

from app.core.observability import observe
from app.core.prompts import prompt_manager
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.analysis.schemas import AgentResponse
from agents.base import BaseAgent
from quant import risk_scanners


class ContrarianAgent(BaseAgent):
    """
    Agent responsible for finding reasons to reject an investment thesis.
    It acts as a professional skeptic, analyzing data for risks, weaknesses, and threats
    by using a suite of deterministic risk-scanning tools.
    """

    def __init__(self, llm_service: LLMServiceInterface, model: str = "mistral-8b"):
        super().__init__(llm_service, model)

    def _get_tools(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "volatility_scanner",
                    "description": "Scans financial data for metrics related to high price volatility.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "debt_load_scanner",
                    "description": "Scans financial data for risks associated with high debt and poor credit health.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "sentiment_alert_scanner",
                    "description": "Scans news and sentiment data for significant negative sentiment.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_bear_case",
                    "description": "Submits the final bear case analysis, including identified risks and a summary.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "bear_case_summary": {
                                "type": "string",
                                "description": "The full, 2-3 paragraph summary of the bear case.",
                            },
                            "identified_risks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "risk_category": {
                                            "type": "string",
                                            "enum": [
                                                "Volatility",
                                                "Debt",
                                                "Sentiment",
                                                "Other",
                                            ],
                                        },
                                        "description": {"type": "string"},
                                        "supporting_data": {"type": "string"},
                                    },
                                    "required": [
                                        "risk_category",
                                        "description",
                                        "supporting_data",
                                    ],
                                },
                                "description": "A structured list of all identified risks from the scanners.",
                            },
                        },
                        "required": ["bear_case_summary", "identified_risks"],
                    },
                },
            },
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Executes the requested tool."""
        try:
            # We pass empty arguments for now as the scanners are placeholders
            if tool_name == "volatility_scanner":
                return json.dumps(risk_scanners.volatility_scanner({}))
            elif tool_name == "debt_load_scanner":
                return json.dumps(risk_scanners.debt_load_scanner({}))
            elif tool_name == "sentiment_alert_scanner":
                return json.dumps(risk_scanners.sentiment_alert_scanner({}))
            elif tool_name == "submit_bear_case":
                return json.dumps(arguments)
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:Contrarian:Execute")
    async def execute(
        self,
        user_query: str,
        step_number: int = 0,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> AgentResponse:
        """
        Executes the agent loop with flexible multi-turn tool usage.
        The agent can use multiple risk-scanning tools in sequence before submitting the final bear case.
        """
        max_turns = 5
        prompt = user_query
        if context_data:
            prompt += f"\n\nHere is the context data you must analyze: {json.dumps(context_data)}"

        messages: List[Message] = [
            Message(
                role="system", content=prompt_manager.get_prompt("contrarian.system")
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
                    if tool_name == "submit_bear_case":
                        final_data = self._execute_tool(tool_name, arguments)
                        return AgentResponse(
                            status="success", data=json.loads(final_data), errors=None
                        )

                    # Otherwise, execute the tool and add result to context
                    tid = await self.emit_status(
                        step_number, tool_name, "Running risk scan...", status="running"
                    )
                    tool_result = self._execute_tool(tool_name, arguments)
                    await self.emit_status(
                        step_number,
                        tool_name,
                        "Running risk scan...",
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
                errors=[f"Agent failed to submit bear case within {max_turns} turns."],
            )

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
