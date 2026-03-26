import json
import pandas as pd
from typing import Dict, Any, Optional, List
from app.core.observability import observe, langfuse_context

from app.core.prompts import prompt_manager
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.analysis.schemas import AgentResponse
from quant.indicators import TechnicalScanner
from agents.base import BaseAgent


class TechnicalAnalysisAgent(BaseAgent):
    """
    Agent responsible for performing technical analysis on price data.
    Uses TechnicalScanner for deterministic calculations and LLM for trend reporting.
    """

    def __init__(self, llm_service: LLMServiceInterface, model: str = "mistral-8b"):
        super().__init__(llm_service, model)
        self.scanner = TechnicalScanner()

    def _get_tools(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_technical_scan",
                    "description": "Calculates technical indicators like RSI, MACD, and Bollinger Bands from OHLCV price data.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ohlcv_data": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "timestamp": {"type": "string"},
                                        "open": {"type": "number"},
                                        "high": {"type": "number"},
                                        "low": {"type": "number"},
                                        "close": {"type": "number"},
                                        "volume": {"type": "number"},
                                    },
                                    "required": ["close"],
                                },
                                "description": "A list of OHLCV dictionaries (at minimum requires 'close' prices).",
                            }
                        },
                        "required": ["ohlcv_data"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_technical_report",
                    "description": "Submits the final technical analysis trend report.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "trend": {
                                "type": "string",
                                "enum": ["Bullish", "Bearish", "Neutral"],
                                "description": "The overall market trend identified.",
                            },
                            "report_summary": {
                                "type": "string",
                                "description": "A 2-3 paragraph professional summary of the technical indicators.",
                            },
                            "key_indicators": {
                                "type": "object",
                                "description": "Key technical indicator values (RSI, MACD, etc.) used in the report.",
                            },
                            "reversal_points": {
                                "type": "array",
                                "items": {"type": "number"},
                                "description": "Potential price reversal levels identified.",
                            },
                        },
                        "required": ["trend", "report_summary", "key_indicators"],
                    },
                },
            },
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Executes the requested tool."""
        try:
            if tool_name == "run_technical_scan":
                ohlcv_list = arguments.get("ohlcv_data", [])
                if not ohlcv_list:
                    return json.dumps({"error": "No OHLCV data provided"})

                df = pd.DataFrame(ohlcv_list)
                scan_results = self.scanner.scan(df)
                return json.dumps(scan_results)
            elif tool_name == "submit_technical_report":
                return json.dumps(arguments)
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:Technical:Execute")
    async def execute(
        self,
        user_query: str,
        step_number: int = 0,
        ohlcv_data: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentResponse:
        """
        Executes the technical analysis loop.
        """
        if ohlcv_data:
            prompt = prompt_manager.get_prompt(
                "technical.user_with_data",
                user_query=user_query,
                ohlcv_data=json.dumps(ohlcv_data),
            )
        else:
            prompt = prompt_manager.get_prompt(
                "technical.user_no_data", user_query=user_query
            )

        messages = [
            Message(
                role="system", content=prompt_manager.get_prompt("technical.system")
            ),
            Message(role="user", content=prompt),
        ]

        try:
            # First call -> run_technical_scan
            response_msg = await self.llm_service.generate_message(
                messages=messages, model=self.model, tools=self._get_tools()
            )
            messages.append(response_msg)

            if not response_msg.tool_calls:
                return AgentResponse(
                    status="success",
                    data={"response": response_msg.content},
                    errors=[
                        "Final output was text-only, not structured JSON via submit_technical_report tool."
                    ],
                )

            # Process tool calls (typically just run_technical_scan)
            for tool_call in response_msg.tool_calls:
                function_call = tool_call.get("function", {})
                tool_name = function_call.get("name")

                if tool_name == "submit_technical_report":
                    continue

                arguments_str = function_call.get("arguments", "{}")
                arguments = (
                    json.loads(arguments_str)
                    if isinstance(arguments_str, str)
                    else arguments_str
                )

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

            # Second call -> submit_technical_report
            final_response_msg = await self.llm_service.generate_message(
                messages=messages, model=self.model, tools=self._get_tools()
            )

            if final_response_msg.tool_calls:
                final_tool_call = final_response_msg.tool_calls[0]
                final_tool_name = final_tool_call.get("function", {}).get("name")
                if final_tool_name == "submit_technical_report":
                    arguments_str = final_tool_call.get("function", {}).get(
                        "arguments", "{}"
                    )
                    arguments = (
                        json.loads(arguments_str)
                        if isinstance(arguments_str, str)
                        else arguments_str
                    )
                    final_data = self._execute_tool(final_tool_name, arguments)
                    return AgentResponse(
                        status="success", data=json.loads(final_data), errors=None
                    )

            return AgentResponse(
                status="success",
                data={"response": final_response_msg.content},
                errors=[
                    "Agent failed to use the submit_technical_report tool on its final step."
                ],
            )

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
