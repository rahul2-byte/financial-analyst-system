import json
from typing import Dict, Any, Optional, List

from app.core.observability import observe
from app.core.prompts import prompt_manager
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.analysis.schemas import AgentResponse
from agents.base import BaseAgent
from quant import macro_scanners


class MacroAnalysisAgent(BaseAgent):
    """
    Agent responsible for analyzing broad economic trends by using a suite
    of deterministic macro-economic scanning tools.
    """

    def __init__(self, llm_service: LLMServiceInterface, model: str = "mistral-8b"):
        super().__init__(llm_service, model)

    def _get_tools(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "interest_rate_scanner",
                    "description": "Scans for current interest rates and central bank stance for a country.",
                    "parameters": {
                        "type": "object", 
                        "properties": {
                            "country": {"type": "string", "description": "The country to scan, e.g., 'USA'."}
                        },
                        "required": ["country"]
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "economic_indicator_scanner",
                    "description": "Scans for a specific key economic indicator like CPI or GDP.",
                    "parameters": {
                        "type": "object", 
                        "properties": {
                            "indicator": {"type": "string", "description": "The indicator to scan, e.g., 'CPI' or 'GDP'."}
                        },
                        "required": ["indicator"]
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "commodity_price_scanner",
                    "description": "Scans for the price of a key commodity.",
                    "parameters": {
                        "type": "object", 
                        "properties": {
                            "commodity": {"type": "string", "description": "The commodity to scan, e.g., 'oil'."}
                        },
                        "required": ["commodity"]
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_macro_outlook",
                    "description": "Submits the final macro-economic outlook.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "outlook_summary": {
                                "type": "string",
                                "description": "The full, 2-3 paragraph summary of the macro-economic outlook.",
                            },
                            "key_indicators": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "indicator_name": {"type": "string"},
                                        "value": {"type": "string"},
                                        "commentary": {"type": "string"}
                                    },
                                    "required": ["indicator_name", "value", "commentary"]
                                },
                                "description": "A structured list of the key indicators and data points from the scan.",
                            },
                        },
                        "required": ["outlook_summary", "key_indicators"],
                    },
                },
            },
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Executes the requested tool."""
        try:
            if tool_name == "interest_rate_scanner":
                return json.dumps(macro_scanners.interest_rate_scanner(**arguments))
            elif tool_name == "economic_indicator_scanner":
                return json.dumps(macro_scanners.economic_indicator_scanner(**arguments))
            elif tool_name == "commodity_price_scanner":
                return json.dumps(macro_scanners.commodity_price_scanner(**arguments))
            elif tool_name == "submit_macro_outlook":
                return json.dumps(arguments)
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:Macro:Execute")
    async def execute(
        self, user_query: str, step_number: int = 0, context_data: Optional[str] = None
    ) -> AgentResponse:
        """
        Executes the agent loop with flexible multi-turn tool usage.
        """
        max_turns = 5
        prompt = user_query
        if context_data:
            prompt += f"\n\nHere is the context data you must analyze: {context_data}"

        messages: List[Message] = [
            Message(
                role="system", content=prompt_manager.get_prompt("macro.system")
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
                        status="failure", data={}, errors=["Agent did not call any tools."]
                    )

                # Execute all tool calls in this turn
                for tool_call in response_msg.tool_calls:
                    function_call = tool_call.get("function", {})
                    tool_name = function_call.get("name")
                    
                    # Parse arguments safely
                    arguments_str = function_call.get("arguments", "{}")
                    try:
                        arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
                    except json.JSONDecodeError:
                        arguments = {}

                    # If it's the final submission tool, we're done
                    if tool_name == "submit_macro_outlook":
                        final_data = self._execute_tool(tool_name, arguments)
                        return AgentResponse(status="success", data=json.loads(final_data), errors=None)

                    # Otherwise, execute the tool and add result to context
                    tid = await self.emit_status(
                        step_number, tool_name, "Scanning macro data...", status="running"
                    )
                    tool_result = self._execute_tool(tool_name, arguments)
                    await self.emit_status(
                        step_number, tool_name, "Scanning macro data...", "Done.", status="completed", tool_id=tid
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
                errors=[f"Agent failed to submit macro outlook within {max_turns} turns."]
            )

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])