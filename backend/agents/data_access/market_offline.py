import json
from typing import Dict, Any
from app.core.observability import observe, langfuse_context

from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.data_access.schemas import AgentResponse
from storage.sql.client import PostgresClient


class MarketOfflineAgent:
    """
    Agent responsible for querying the local PostgreSQL database
    to determine what market data is already available offline.
    """

    SYSTEM_PROMPT = """
You are the Market Offline Data Agent for a Financial Intelligence Platform.
Your sole responsibility is to query the local PostgreSQL database using the provided tools to answer the user's question about what data we have offline.

CRITICAL RULES:
1. You DO NOT perform any math or financial calculations.
2. You MUST use the tools provided to you to fetch the answer.
3. You return the final answer to the user in a clear, concise manner based on the tool's output.
4. Always respond with JSON matching the AgentResponse schema at the end.
    """

    def __init__(
        self,
        llm_service: LLMServiceInterface,
        db_client: PostgresClient,
        model: str = "mistral-8b",
    ):
        self.llm = llm_service
        self.db = db_client
        self.model = model

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
                    "name": "get_db_info",
                    "description": "Gets overall database information: total tickers, table count, DB size, and if there is any data.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_ticker_info",
                    "description": "Gets specific info for a stock ticker: date ranges, row counts, and data frequency.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "The stock ticker symbol (e.g., 'AAPL').",
                            }
                        },
                        "required": ["ticker"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_ticker_data",
                    "description": "Deletes all offline data for a specific stock ticker.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "The stock ticker symbol to delete.",
                            }
                        },
                        "required": ["ticker"],
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

            elif tool_name == "get_db_info":
                has_data = self.db.has_any_data()
                tickers = self.db.get_ticker_count()
                tables = self.db.get_table_count()
                size = self.db.get_db_size()
                return json.dumps(
                    {
                        "has_data": has_data,
                        "total_tickers": tickers,
                        "total_tables": tables,
                        "db_size": size,
                    }
                )

            elif tool_name == "get_ticker_info":
                ticker = arguments.get("ticker", "")
                info = self.db.get_ticker_info(ticker)
                return json.dumps(info)

            elif tool_name == "delete_ticker_data":
                ticker = arguments.get("ticker", "")
                deleted_rows = self.db.delete_ticker_data(ticker)
                return json.dumps(
                    {"ticker": ticker, "deleted_rows": deleted_rows, "success": True}
                )

            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})

        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:MarketOffline:Execute")
    async def execute(self, user_query: str) -> AgentResponse:
        """
        Executes the agent loop:
        1. Sends query to LLM with tools
        2. LLM optionally calls tool
        3. Agent runs tool and sends result back to LLM
        4. LLM formulates final answer
        """
        messages = [
            Message(role="system", content=self.SYSTEM_PROMPT),
            Message(role="user", content=user_query),
        ]

        try:
            # 1. First LLM call, providing tools
            response_msg = await self.llm.generate_message(
                messages=messages, model=self.model, tools=self._get_tools()
            )

            messages.append(response_msg)

            # 2. Check if LLM wants to call a tool
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

                    # 3. Execute tool
                    tool_result = self._execute_tool(tool_name, arguments)

                    langfuse_context.update_current_observation(
                        metadata={
                            "tool_name": tool_name,
                            "tool_args": arguments,
                            "tool_result": tool_result,
                        }
                    )

                    # Append tool result to messages
                    messages.append(
                        Message(
                            role="tool",
                            content=tool_result,
                            name=tool_name,
                            tool_call_id=tool_call.get("id"),
                        )
                    )

                # 4. LLM formulates final answer
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
