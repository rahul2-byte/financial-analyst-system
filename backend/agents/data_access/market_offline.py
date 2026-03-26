import json
from typing import Dict, Any, List
from unittest.mock import AsyncMock
from app.core.observability import observe, langfuse_context

from app.core.prompts import prompt_manager
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.data_access.schemas import AgentResponse
from storage.sql.client import PostgresClient
from agents.base import BaseAgent


class MarketOfflineAgent(BaseAgent):
    """
    Agent responsible for querying the local PostgreSQL database
    to determine what market data is already available offline.
    """

    def __init__(
        self,
        llm_service: LLMServiceInterface,
        db_client: PostgresClient,
        model: str = "mistral-8b",
    ):
        super().__init__(llm_service, model)
        self.db = db_client

    def _get_tools(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "check_db_status",
                    "description": "Checks if the PostgreSQL database is up and running.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_table_names",
                    "description": "Gets a list of all table names in the database.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_column_names",
                    "description": "Gets a list of column names for a specific table.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "The name of the table to inspect.",
                            }
                        },
                        "required": ["table_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_ticker_info",
                    "description": "Gets specific info for a stock ticker: date ranges, row counts, and if it was found.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "The stock ticker symbol (e.g., 'RELIANCE.NS').",
                            }
                        },
                        "required": ["ticker"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_offline_status",
                    "description": "Submits the final determination of whether the data is available offline.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "data_available": {"type": "boolean"},
                            "summary": {
                                "type": "string",
                                "description": "Brief explanation of why the data is or is not available.",
                            },
                        },
                        "required": ["data_available", "summary"],
                    },
                },
            },
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute the requested tool and return the JSON result as string."""
        try:
            if tool_name == "check_db_status":
                status = self.db.is_db_up()
                return json.dumps({"db_up": status})

            elif tool_name == "get_table_names":
                tables = self.db.get_table_names()
                return json.dumps({"tables": tables})

            elif tool_name == "get_column_names":
                table_name = arguments.get("table_name", "")
                columns = self.db.get_column_names(table_name)
                return json.dumps({"table": table_name, "columns": columns})

            elif tool_name == "get_ticker_info":
                ticker = arguments.get("ticker", "")
                info = self.db.get_ticker_info(ticker)
                return json.dumps(info)

            elif tool_name == "submit_offline_status":
                return json.dumps(arguments)

            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})

        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:MarketOffline:Execute")
    async def execute(self, user_query: str, step_number: int = 0) -> AgentResponse:
        """
        Executes the agent loop with sequential tool calling.
        """
        messages = [
            Message(
                role="system",
                content=prompt_manager.get_prompt("market_offline.system"),
            ),
            Message(role="user", content=user_query),
        ]

        max_turns = 10
        current_turn = 0

        try:
            while current_turn < max_turns:
                response_msg_obj = await self.llm_service.generate_message(
                    messages=messages, model=self.model, tools=self._get_tools()
                )

                # Handle AsyncMock wrapping the Message object in tests
                if isinstance(response_msg_obj, AsyncMock):
                    response_msg = response_msg_obj.return_value
                else:
                    response_msg = response_msg_obj

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
                        if tool_name == "submit_offline_status":
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
                            "Final output was text-only, not structured JSON via submit_offline_status tool."
                        ],
                    )

            return AgentResponse(
                status="failure",
                data={},
                errors=[f"Agent failed to submit results within {max_turns} turns."],
            )

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
