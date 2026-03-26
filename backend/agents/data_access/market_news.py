import json
from typing import Dict, Any, List

from app.core.prompts import prompt_manager
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.data_access.schemas import AgentResponse
from data.providers.rss_news import RSSNewsFetcher
from storage.vector.client import QdrantStorage
from data.processors.text import TextProcessor
from agents.base import BaseAgent


class MarketNewsAgent(BaseAgent):
    """
    Agent responsible for fetching unstructured market news from RSS feeds.
    """

    def __init__(
        self,
        llm_service: LLMServiceInterface,
        rss_fetcher: RSSNewsFetcher,
        vector_db: QdrantStorage,
        model: str = "mistral-8b",
    ):
        super().__init__(llm_service, model)
        self.rss = rss_fetcher
        self.vector_db = vector_db
        self.text_processor = TextProcessor()

    def _get_tools(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "fetch_market_news",
                    "description": "Fetch latest news headlines and summaries from RSS feeds.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "description": "News category: 'general', 'markets', 'companies', or 'economy'.",
                            }
                        },
                        "required": ["category"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "save_news_to_vector_db",
                    "description": "Processes and saves a list of news articles to the vector database.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "news_articles": {
                                "type": "array",
                                "items": {"type": "object"},
                            }
                        },
                        "required": ["news_articles"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_news_results",
                    "description": "Submits the final summary of fetched or saved news articles.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "status": {
                                "type": "string",
                                "enum": ["success", "failure", "error"],
                            },
                            "articles_processed": {"type": "integer"},
                            "summary": {
                                "type": "string",
                                "description": "Brief summary of the news retrieval and status of the save operation.",
                            },
                        },
                        "required": ["status", "articles_processed", "summary"],
                    },
                },
            },
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        try:
            if tool_name == "fetch_market_news":
                category = arguments.get("category", "general")
                news_list = self.rss.fetch_market_news(category)
                return json.dumps(news_list)

            elif tool_name == "save_news_to_vector_db":
                articles = arguments.get("news_articles", [])
                if not articles:
                    return json.dumps(
                        {"status": "failure", "error": "No articles to save"}
                    )

                all_chunks = []
                for item in articles:
                    content = f"{item.get('title', '')}\n\n{item.get('summary', '')}"
                    metadata = {
                        "source": "RSS",
                        "link": item.get("link", ""),
                        "published": item.get("published", ""),
                    }
                    chunks = self.text_processor.process_and_embed(
                        content, metadata=metadata
                    )
                    all_chunks.extend(chunks)

                if all_chunks:
                    self.vector_db.upsert_chunks(all_chunks)

                return json.dumps(
                    {"status": "success", "saved_articles": len(articles)}
                )

            elif tool_name == "submit_news_results":
                return json.dumps(arguments)

            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def execute(self, user_query: str, step_number: int = 0) -> AgentResponse:
        messages = [
            Message(
                role="system", content=prompt_manager.get_prompt("market_news.system")
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
                        if tool_name == "submit_news_results":
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
                            "Final output was text-only, not structured JSON via submit_news_results tool."
                        ],
                    )

            return AgentResponse(
                status="failure",
                data={},
                errors=[f"Agent failed to submit results within {max_turns} turns."],
            )
        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
