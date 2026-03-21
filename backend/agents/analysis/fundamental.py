import json
from typing import Dict, Any, Optional
from app.core.observability import observe, langfuse_context

from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.analysis.schemas import AgentResponse
from quant.fundamentals import FundamentalScanner


class FundamentalAnalysisAgent:
    """
    Agent responsible for analyzing structured financial data.
    It strictly uses the FundamentalScanner to perform quantitative evaluations
    and uses the LLM solely to synthesize the deterministic output into a readable thesis.
    """

    SYSTEM_PROMPT = """
You are the Fundamental Analysis Agent for a Financial Intelligence Platform.
Your job is to read raw financial data, pass it to your deterministic analysis tool, and write a professional investment thesis based ONLY on the tool's output.

CRITICAL RULES:
1. You DO NOT perform any math or ratio calculations yourself.
2. You MUST use the `run_fundamental_scan` tool to evaluate the raw data.
3. Your final response should be a 2-3 paragraph professional Value Investment Thesis synthesizing the tool's output. Do not hallucinate numbers.
4. Always respond with JSON matching the AgentResponse schema at the end.
    """

    def __init__(self, llm_service: LLMServiceInterface, model: str = "mistral-8b"):
        self.llm = llm_service
        self.model = model
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
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:Fundamental:Execute")
    async def execute(
        self, user_query: str, raw_fundamental_data: Optional[Dict[str, Any]] = None
    ) -> AgentResponse:
        """
        Executes the agent loop.
        If raw_fundamental_data is provided directly, we inject it into the prompt.
        """
        prompt = user_query
        if raw_fundamental_data:
            prompt += f"\n\nHere is the raw data you must analyze: {json.dumps(raw_fundamental_data)}"

        messages = [
            Message(role="system", content=self.SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ]

        try:
            response_msg = await self.llm.generate_message(
                messages=messages, model=self.model, tools=self._get_tools()
            )

            messages.append(response_msg)

            if response_msg.tool_calls:
                for tool_call in response_msg.tool_calls:
                    function_call = tool_call.get("function", {})
                    tool_name = function_call.get("name")
                    arguments_str = function_call.get("arguments", "{}")

                    if isinstance(arguments_str, str):
                        try:
                            arguments = json.loads(arguments_str)
                        except json.JSONDecodeError:
                            arguments = {}
                    else:
                        arguments = arguments_str

                    tool_result = self._execute_tool(tool_name, arguments)

                    langfuse_context.update_current_observation(
                        metadata={
                            "tool_name": tool_name,
                            "tool_args": arguments,
                            "tool_result": tool_result,
                        }
                    )

                    messages.append(
                        Message(
                            role="tool",
                            content=tool_result,
                            name=tool_name,
                            tool_call_id=tool_call.get("id"),
                        )
                    )

                final_response_msg = await self.llm.generate_message(
                    messages=messages, model=self.model
                )
                final_content = final_response_msg.content
            else:
                final_content = response_msg.content

            return AgentResponse(
                status="success", data={"response": final_content}, errors=None
            )

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
