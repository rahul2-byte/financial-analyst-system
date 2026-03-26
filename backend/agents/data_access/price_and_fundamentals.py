import json
from typing import Dict, Any, List

from app.core.prompts import prompt_manager
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.data_access.schemas import AgentResponse
from data.providers.yfinance import YFinanceFetcher
from storage.sql.client import PostgresClient
from data.schemas.market import OHLCVData
from agents.base import BaseAgent

class PriceAndFundamentalsAgent(BaseAgent):
    """
    Agent responsible for fetching ticker-specific, structured data like
    price history and company fundamentals from online sources.
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
                    "name": "fetch_stock_price",
                    "description": "Fetch historical pricing data (OHLCV) for a stock ticker.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string", "description": "Stock ticker symbol."},
                            "period": {"type": "string", "description": "Data period (e.g., '1y')."},
                            "interval": {"type": "string", "description": "Data interval (e.g., '1d')."},
                        },
                        "required": ["ticker"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "save_ohlcv_to_db",
                    "description": "Saves a list of OHLCV data to the database.",
                    "parameters": {
                        "type": "object",
                        "properties": {"price_data": {"type": "object"}},
                        "required": ["price_data"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_company_fundamentals",
                    "description": "Fetch company fundamental metrics.",
                    "parameters": {
                        "type": "object",
                        "properties": {"ticker": {"type": "string"}},
                        "required": ["ticker"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "save_fundamentals_to_db",
                    "description": "Saves company fundamental data to the database.",
                    "parameters": {
                        "type": "object",
                        "properties": {"fundamentals_data": {"type": "object"}},
                        "required": ["fundamentals_data"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_data_results",
                    "description": "Submits the final summary of fetched or saved data.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "action_taken": {"type": "string", "enum": ["FETCHED", "SAVED", "FETCHED_AND_SAVED", "ERROR"]},
                            "data_type": {"type": "string", "enum": ["PRICE", "FUNDAMENTALS", "BOTH", "NONE"]},
                            "summary": {"type": "string", "description": "Brief summary of the data retrieved or status of the save operation."}
                        },
                        "required": ["ticker", "action_taken", "data_type", "summary"]
                    }
                }
            }
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        try:
            if tool_name == "fetch_stock_price":
                ticker = arguments.get("ticker", "")
                period = arguments.get("period", "1mo")
                interval = arguments.get("interval", "1d")
                data = self.yf.fetch_stock_price(ticker, period, interval)
                return json.dumps(data)

            elif tool_name == "save_ohlcv_to_db":
                price_data = arguments.get("price_data", {})
                if "data" in price_data and isinstance(price_data["data"], list):
                    from datetime import datetime
                    ohlcv_list = [OHLCVData(
                        ticker=price_data["ticker"],
                        date=datetime.fromisoformat(d["Date"]) if "Date" in d else datetime.fromisoformat(d["Datetime"]),
                        open=d.get("Open", 0.0),
                        high=d.get("High", 0.0),
                        low=d.get("Low", 0.0),
                        close=d.get("Close", 0.0),
                        volume=int(d.get("Volume", 0)),
                        adjusted_close=d.get("Adj Close"),
                    ) for d in price_data["data"]]
                    self.sql_db.save_ohlcv(ohlcv_list)
                    return json.dumps({"status": "success", "saved_records": len(ohlcv_list)})
                return json.dumps({"status": "failure", "error": "No data to save"})

            elif tool_name == "fetch_company_fundamentals":
                ticker = arguments.get("ticker", "")
                data = self.yf.fetch_company_fundamentals(ticker)
                return json.dumps(data)

            elif tool_name == "save_fundamentals_to_db":
                fundamentals_data = arguments.get("fundamentals_data", {})
                if "error" not in fundamentals_data:
                    self.sql_db.upsert_fundamentals(fundamentals_data)
                    return json.dumps({"status": "success", "ticker": fundamentals_data.get("ticker")})
                return json.dumps({"status": "failure", "error": "No fundamentals to save"})
            
            elif tool_name == "submit_data_results":
                return json.dumps(arguments)
                
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def execute(self, user_query: str, step_number: int = 0) -> AgentResponse:
        messages = [
            Message(role="system", content=prompt_manager.get_prompt("price_and_fundamentals.system")),
            Message(role="user", content=user_query),
        ]
        
        max_turns = 10
        current_turn = 0

        try:
            while current_turn < max_turns:
                response_data = await self.llm_service.generate_message(
                    messages=messages, model=self.model, tools=self._get_tools()
                )
                
                response_msg = Message(**response_data) if isinstance(response_data, dict) else response_data
                messages.append(response_msg)

                if response_msg.tool_calls:
                    for tool_call in response_msg.tool_calls:
                        tool_name = tool_call.get("function", {}).get("name")
                        arguments_str = tool_call.get("function", {}).get("arguments", "{}")
                        
                        try:
                            arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
                        except json.JSONDecodeError:
                            arguments = {}

                        # Check if it's the final submission tool
                        if tool_name == "submit_data_results":
                            final_data = self._execute_tool(tool_name, arguments)
                            return AgentResponse(status="success", data=json.loads(final_data), errors=None)

                        # Otherwise, execute the tool and continue the loop
                        tool_result = self._execute_tool(tool_name, arguments)
                        messages.append(Message(role="tool", content=tool_result, name=tool_name, tool_call_id=tool_call.get("id")))
                    
                    current_turn += 1
                else:
                    # If the LLM returns text without calling a tool, we treat it as the final content but flag it.
                    return AgentResponse(
                        status="success", 
                        data={"response": response_msg.content}, 
                        errors=["Final output was text-only, not structured JSON via submit_data_results tool."]
                    )
            
            # If the loop finishes without a 'submit_data_results' call.
            return AgentResponse(
                status="failure",
                data={},
                errors=[f"Agent failed to submit results within {max_turns} turns."]
            )

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
