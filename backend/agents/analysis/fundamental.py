import json
from typing import Dict, Any, Optional, List
from app.core.observability import observe, langfuse_context
from app.core.prompts import prompt_manager
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.analysis.schemas import AgentResponse
from quant.fundamentals import FundamentalScanner
from agents.base import BaseAgent


class FundamentalAnalysisAgent(BaseAgent):
    """
    Agent responsible for analyzing structured financial data.
    It strictly uses the FundamentalScanner to perform quantitative evaluations
    and uses the LLM solely to synthesize the deterministic output into a readable thesis.
    """

    def __init__(self, llm_service: LLMServiceInterface, model: str = "mistral-8b"):
        super().__init__(llm_service, model)
        self.scanner = FundamentalScanner()

    def _get_tools(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_fundamental_scan",
                    "description": "Runs deterministic quantitative analysis on raw financial data to evaluate valuation, health, and profitability.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "raw_data": {
                                "type": "string",
                                "description": "The raw JSON string of fundamental data.",
                            }
                        },
                        "required": ["raw_data"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_thesis",
                    "description": "Submits the final investment thesis and key findings.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "investment_thesis": {
                                "type": "string",
                                "description": "The full, 2-3 paragraph investment thesis.",
                            },
                            "key_findings": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "A bulleted list of the most critical data points from the scan.",
                            },
                            "confidence_score": {
                                "type": "number",
                                "description": "A score from 0.0 to 1.0 indicating confidence in the thesis, based on the strength of the data.",
                            },
                        },
                        "required": ["investment_thesis", "key_findings", "confidence_score"],
                    },
                },
            }
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Executes the requested tool."""
        try:
            if tool_name == "run_fundamental_scan":
                raw_data_str = arguments.get("raw_data", "{}")
                if isinstance(raw_data_str, str):
                    try:
                        raw_data = json.loads(raw_data_str)
                    except json.JSONDecodeError:
                        raw_data = {}
                else:
                    raw_data = raw_data_str

                scan_results = self.scanner.scan(raw_data)
                return json.dumps(scan_results)
            elif tool_name == "submit_thesis":
                return json.dumps(arguments)
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:Fundamental:Execute")
    async def execute(
        self,
        user_query: str,
        step_number: int = 0,
        raw_fundamental_data: Optional[Dict[str, Any]] = None,
    ) -> AgentResponse:
        """
        Executes the agent loop with flexible multi-turn tool usage.
        The agent can use multiple tools in sequence before submitting the final thesis.
        """
        max_turns = 5
        prompt = user_query
        if raw_fundamental_data:
            prompt += f"\n\nHere is the raw data you must analyze: {json.dumps(raw_fundamental_data)}"

        messages: List[Message] = [
            Message(
                role="system", content=prompt_manager.get_prompt("fundamental.system")
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
                        status="success", 
                        data={"response": response_msg.content}, 
                        errors=["Agent did not call any tools."]
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
                    if tool_name == "submit_thesis":
                        final_data = self._execute_tool(tool_name, arguments)
                        return AgentResponse(status="success", data=json.loads(final_data), errors=None)

                    # Otherwise, execute the tool and add result to context
                    tid = await self.emit_status(
                        step_number, tool_name, "Processing tool...", status="running"
                    )
                    tool_result = self._execute_tool(tool_name, arguments)
                    await self.emit_status(
                        step_number, tool_name, "Processing tool...", "Done.", status="completed", tool_id=tid
                    )

                    langfuse_context.update_current_observation(
                        metadata={"tool_name": tool_name, "tool_args": arguments, "tool_result": tool_result}
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
                errors=[f"Agent failed to submit thesis within {max_turns} turns."]
            )

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])