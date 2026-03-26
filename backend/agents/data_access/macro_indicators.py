import json
from typing import Dict, Any, List

from app.core.prompts import prompt_manager
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.data_access.schemas import AgentResponse
from data.providers.yfinance import YFinanceFetcher
from storage.sql.client import PostgresClient
from agents.base import BaseAgent


class MacroIndicatorsAgent(BaseAgent):
    """
    Agent responsible for fetching global macro-economic indicators.
    """

    def __init__(
        self,
        llm_service: LLMServiceInterface,
        yf_fetcher: YFinanceFetcher,
        sql_db: PostgresClient,
        model: str = "mistral-8b",
    ):
        super().__init__(llm_service, model)
        self.yf = yf_fetcher
        self.sql_db = sql_db

    def _get_tools(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "fetch_macro_indicators",
                    "description": "Fetch current macro indicators (Nifty 50, VIX, USD/INR, Crude Oil, Gold).",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "save_macro_indicators_to_db",
                    "description": "Saves macro indicator data to the database.",
                    "parameters": {
                        "type": "object",
                        "properties": {"macro_data": {"type": "object"}},
                        "required": ["macro_data"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_macro_results",
                    "description": "Submits the final summary of fetched or saved macro indicators.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "status": {
                                "type": "string",
                                "enum": ["success", "failure", "error"],
                            },
                            "summary": {
                                "type": "string",
                                "description": "Brief summary of the macro data retrieval and status of the save operation.",
                            },
                        },
                        "required": ["status", "summary"],
                    },
                },
            },
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        try:
            if tool_name == "fetch_macro_indicators":
                data = self.yf.fetch_macro_indicators()
                return json.dumps(data)

            elif tool_name == "save_macro_indicators_to_db":
                macro_data = arguments.get("macro_data", {})
                if "error" not in macro_data:
                    self.sql_db.upsert_macro_indicators(macro_data)
                    return json.dumps({"status": "success"})
                return json.dumps(
                    {"status": "failure", "error": "No macro data to save"}
                )

            elif tool_name == "submit_macro_results":
                return json.dumps(arguments)

            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def execute(self, user_query: str, step_number: int = 0) -> AgentResponse:
        messages = [
            Message(
                role="system",
                content=prompt_manager.get_prompt("macro_indicators.system"),
            ),
            Message(role="user", content=user_query),
        ]

        max_turns = 10
        current_turn = 0

        try:
            while current_turn < max_turns:
                response_data = await self.llm_service.generate_message(
                    messages=messages, model=self.model, tools=self._get_tools()
                )

                response_msg = (
                    Message(**response_data)
                    if isinstance(response_data, dict)
                    else response_data
                )
                messages.append(response_msg)

                if response_msg.tool_calls:
                    for tool_call in response_msg.tool_calls:
                        tool_name = tool_call.get("function", {}).get("name")
                        arguments_str = tool_call.get("function", {}).get(
                            "arguments", "{}"
                        )

                        try:
                            arguments = (
                                json.loads(arguments_str)
                                if isinstance(arguments_str, str)
                                else arguments_str
                            )
                        except json.JSONDecodeError:
                            arguments = {}

                        # Check if it's the final submission tool
                        if tool_name == "submit_macro_results":
                            final_data = self._execute_tool(tool_name, arguments)
                            return AgentResponse(
                                status="success",
                                data=json.loads(final_data),
                                errors=None,
                            )

                        # Otherwise, execute the tool and continue the loop
                        tool_result = self._execute_tool(tool_name, arguments)
                        messages.append(
                            Message(
                                role="tool",
                                content=tool_result,
                                name=tool_name,
                                tool_call_id=tool_call.get("id"),
                            )
                        )

                    current_turn += 1
                else:
                    return AgentResponse(
                        status="success",
                        data={"response": response_msg.content},
                        errors=[
                            "Final output was text-only, not structured JSON via submit_macro_results tool."
                        ],
                    )

            return AgentResponse(
                status="failure",
                data={},
                errors=[f"Agent failed to submit results within {max_turns} turns."],
            )
        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
