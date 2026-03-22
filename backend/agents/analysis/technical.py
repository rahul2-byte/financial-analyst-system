import json
import pandas as pd
from typing import Dict, Any, Optional, List
from app.core.observability import observe, langfuse_context

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

    SYSTEM_PROMPT = """
You are the Technical Analysis Agent for a Financial Intelligence Platform.
Your job is to read historical price data (OHLCV), pass it to your deterministic technical analysis tool, and write a professional trend report based ONLY on the tool's output.

CRITICAL RULES:
1. You DO NOT perform any math or indicator calculations yourself.
2. You MUST use the `run_technical_scan` tool.
3. Your final response should summarize the trend (Bullish/Bearish), key momentum indicators, and potential reversal points.
4. Always respond with JSON matching the AgentResponse schema.
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
            }
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
        prompt = user_query
        if ohlcv_data:
            prompt += f"\n\nHere is the historical price data for analysis: {json.dumps(ohlcv_data)}"

        messages = [
            Message(role="system", content=self.SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ]

        try:
            tid_strat = await self.emit_status(
                step_number, self.agent_name, "Generating technical report...", status="running"
            )
            response_msg = await self.llm_service.generate_message(
                messages=messages, model=self.model, tools=self._get_tools()
            )
            await self.emit_status(
                step_number, self.agent_name, "Generating technical report...", "Strategy generated.", status="completed", tool_id=tid_strat
            )

            if not response_msg.content:
                response_msg.content = "Calling tool..."

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

                    tid = await self.emit_status(
                        step_number, tool_name, "Calculating technical indicators...", status="running"
                    )
                    tool_result = self._execute_tool(tool_name, arguments)
                    await self.emit_status(
                        step_number,
                        tool_name,
                        "Calculating technical indicators...",
                        "Scan complete.",
                        status="completed",
                        tool_id=tid,
                    )

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

                if messages[-1].role == "tool":
                    tid_proc = await self.emit_status(
                        step_number, self.agent_name, "Processing scan results...", status="running"
                    )
                    intermediate_msg = await self.llm_service.generate_message(
                        messages=messages, model=self.model
                    )
                    if not intermediate_msg.content:
                        intermediate_msg.content = "Processed tool results."
                    await self.emit_status(
                        step_number, self.agent_name, "Processing scan results...", "Results processed.", status="completed", tool_id=tid_proc
                    )
                    messages.append(intermediate_msg)

                tid_synth = await self.emit_status(
                    step_number, self.agent_name, "Synthesizing trend report...", status="running"
                )
                schema_str = json.dumps(AgentResponse.model_json_schema())
                messages.append(
                    Message(
                        role="user",
                        content=(
                            f"The technical scan is complete. Please provide your professional trend report based on these findings as a JSON object matching this schema: {schema_str}\n\n"
                            "CRITICAL: You MUST return ONLY valid JSON. Do not wrap your response in markdown backticks (```json). "
                            "Do not include any conversational text or explanations."
                        ),
                    )
                )

                final_response_msg = await self.llm_service.generate_message(
                    messages=messages,
                    model=self.model,
                    response_format={"type": "json_object"},
                )
                await self.emit_status(
                    step_number, self.agent_name, "Synthesizing trend report...", "Synthesis complete.", status="completed", tool_id=tid_synth
                )
                final_content = final_response_msg.content
            else:
                final_content = response_msg.content

            # The agent is supposed to return an AgentResponse object, but here it's wrapping raw string
            # if we forced JSON, final_content should be parsable. Wait, AgentResponse expects data={"response": string}
            # Actually, the original code returned: AgentResponse(status="success", data={"response": final_content}, errors=None)
            # If we force JSON matching AgentResponse schema, it will return the whole schema. Let's just return the parsed JSON.
            try:
                if not final_content:
                    raise ValueError("Final content is empty")

                from app.core.utils import clean_json_string

                cleaned_content = clean_json_string(final_content)
                parsed_insights = json.loads(cleaned_content)

                # Check if the LLM returned the outer AgentResponse wrapper or just the inner data
                if (
                    isinstance(parsed_insights, dict)
                    and "data" in parsed_insights
                    and "status" in parsed_insights
                ):
                    return AgentResponse(**parsed_insights)
                else:
                    return AgentResponse(
                        status="success",
                        data=(
                            {"response": json.dumps(parsed_insights)}
                            if isinstance(parsed_insights, dict)
                            else {"response": str(parsed_insights)}
                        ),
                        errors=None,
                    )
            except Exception:
                return AgentResponse(
                    status="success", data={"response": final_content}, errors=None
                )

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
