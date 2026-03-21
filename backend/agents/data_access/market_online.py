import json
from typing import Dict, Any
from app.core.observability import observe, langfuse_context

from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.data_access.schemas import AgentResponse
from data.providers.yfinance import YFinanceFetcher
from data.providers.rss_news import RSSNewsFetcher
from storage.sql.client import PostgresClient
from storage.vector.client import QdrantStorage
from data.processors.text import TextProcessor
from data.schemas.market import OHLCVData


class MarketOnlineAgent:
    """
    Agent responsible for fetching real-time and historical market data,
    fundamentals, and news from the internet (focusing on Indian markets).
    It also ensures that any data fetched is stored locally for future use.
    """

    SYSTEM_PROMPT = """
You are the Market Online Data Agent for a Financial Intelligence Platform.
Your sole responsibility is to fetch real-time and historical data from the internet (focusing on Indian markets) to answer the user's query.

CRITICAL RULES:
1. You DO NOT perform any math or financial calculations.
2. You MUST use the tools provided to you to fetch the answer.
3. For Indian stocks, if the user doesn't specify an exchange, the tools automatically handle appending .NS for NSE.
4. You return the final answer to the user in a clear, concise manner based on the tool's output.
5. Always respond with JSON matching the AgentResponse schema at the end.
    """

    def __init__(
        self,
        llm_service: LLMServiceInterface,
        yf_fetcher: YFinanceFetcher,
        rss_fetcher: RSSNewsFetcher,
        sql_db: PostgresClient,
        vector_db: QdrantStorage,
        model: str = "mistral-8b",
    ):
        self.llm = llm_service
        self.yf = yf_fetcher
        self.rss = rss_fetcher
        self.sql_db = sql_db
        self.vector_db = vector_db
        self.text_processor = TextProcessor()
        self.model = model

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
                            "ticker": {
                                "type": "string",
                                "description": "Stock ticker symbol (e.g., RELIANCE, TCS).",
                            },
                            "period": {
                                "type": "string",
                                "description": "Data period (e.g., '1d', '5d', '1mo', '3mo', '1y'). Default '1mo'.",
                            },
                            "interval": {
                                "type": "string",
                                "description": "Data interval (e.g., '1m', '15m', '1h', '1d', '1wk'). Default '1d'.",
                            },
                        },
                        "required": ["ticker"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_company_fundamentals",
                    "description": "Fetch company fundamental metrics like P/E, Market Cap, Debt, Margins, etc.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "Stock ticker symbol.",
                            }
                        },
                        "required": ["ticker"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_financial_statements",
                    "description": "Fetch raw financial statements (Income Statement, Balance Sheet, Cash Flow).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "Stock ticker symbol.",
                            }
                        },
                        "required": ["ticker"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_market_news",
                    "description": "Fetch latest news headlines and summaries.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "description": "Category: 'general', 'markets', 'companies', or 'economy'.",
                            }
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_macro_indicators",
                    "description": "Fetch current macro indicators (Nifty 50, VIX, USD/INR, Crude Oil, Gold).",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute the requested tool, save data to DB, and return the JSON result."""
        try:
            if tool_name == "fetch_stock_price":
                ticker = arguments.get("ticker", "")
                period = arguments.get("period", "1mo")
                interval = arguments.get("interval", "1d")
                price_data = self.yf.fetch_stock_price(ticker, period, interval)

                # Auto-save OHLCV to SQL if it's daily data
                if (
                    interval == "1d"
                    and "data" in price_data
                    and isinstance(price_data["data"], list)
                ):
                    from datetime import datetime

                    ohlcv_list = []
                    for d in price_data["data"]:
                        try:
                            # Try to parse date string back to datetime
                            dt = (
                                datetime.fromisoformat(d["Date"])
                                if "Date" in d
                                else datetime.fromisoformat(d["Datetime"])
                            )
                            ohlcv_list.append(
                                OHLCVData(
                                    ticker=price_data["ticker"],
                                    date=dt,
                                    open=d.get("Open", 0.0),
                                    high=d.get("High", 0.0),
                                    low=d.get("Low", 0.0),
                                    close=d.get("Close", 0.0),
                                    volume=int(d.get("Volume", 0)),
                                    adjusted_close=d.get("Adj Close"),
                                )
                            )
                        except Exception:
                            continue
                    if ohlcv_list:
                        self.sql_db.save_ohlcv(ohlcv_list)

                # TRUNCATION: Don't pass massive price history back to LLM context
                # Just pass the first 5 and last 5 records if data is too long
                if "data" in price_data and len(price_data["data"]) > 20:
                    summary_data = (
                        price_data["data"][:5]
                        + [{"note": "... data truncated ..."}]
                        + price_data["data"][-5:]
                    )
                    price_data["data_summary"] = summary_data
                    del price_data["data"]  # Remove the full list to save tokens

                return json.dumps(price_data)

            elif tool_name == "fetch_company_fundamentals":
                ticker = arguments.get("ticker", "")
                fundamentals = self.yf.fetch_company_fundamentals(ticker)

                # Auto-save Fundamentals to SQL
                if "error" not in fundamentals:
                    self.sql_db.upsert_fundamentals(fundamentals)

                return json.dumps(fundamentals)

            elif tool_name == "fetch_financial_statements":
                ticker = arguments.get("ticker", "")
                statements = self.yf.fetch_financial_statements(ticker)

                # Auto-save Financial Statements to SQL
                if "error" not in statements:
                    self.sql_db.upsert_financial_statements(statements)

                # TRUNCATION: Financial statements can be huge JSONs.
                # We can't easily truncate but we can summarize or just return a note
                # if the user didn't ask for specific deep dive.
                # For now, let's just ensure we don't blow up the context.
                return json.dumps(statements)[
                    :5000
                ]  # Hard truncate string length as safety

            elif tool_name == "fetch_market_news":
                category = arguments.get("category", "general")
                news_list = self.rss.fetch_market_news(category)

                # Auto-save News to Vector DB (RAG)
                for item in news_list:
                    content = f"{item['title']}\n\n{item['summary']}"
                    metadata = {
                        "source": "RSS",
                        "category": category,
                        "link": item["link"],
                    }
                    chunks = self.text_processor.process_and_embed(
                        content, metadata=metadata
                    )
                    self.vector_db.upsert_chunks(chunks)

                return json.dumps(news_list)

            elif tool_name == "fetch_macro_indicators":
                macros = self.yf.fetch_macro_indicators()

                # Auto-save Macro Indicators to SQL
                if "error" not in macros:
                    self.sql_db.upsert_macro_indicators(macros)

                return json.dumps(macros)

            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})

        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Error executing tool {tool_name}: {e}")
            return json.dumps({"error": str(e)})

    @observe(name="Agent:MarketOnline:Execute")
    async def execute(self, user_query: str) -> AgentResponse:
        messages = [
            Message(role="system", content=self.SYSTEM_PROMPT),
            Message(role="user", content=user_query),
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
