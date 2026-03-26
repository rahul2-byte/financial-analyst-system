import json
from typing import Dict, Any, Optional, List
from app.core.observability import observe, langfuse_context

from app.core.prompts import prompt_manager
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.research.schemas import AgentResponse, WebResearchResult
from data.providers.web_search import WebSearchProvider
from agents.base import BaseAgent


class WebSearchAgent(BaseAgent):
    """
    Agent responsible for browsing the internet dynamically using DuckDuckGo
    to answer highly specific, real-time, or niche contextual questions.
    """

    def __init__(
        self,
        llm_service: LLMServiceInterface,
        model: str = "mistral-8b",
        provider: Optional[WebSearchProvider] = None,
    ):
        super().__init__(llm_service, model)
        self.provider = provider if provider else WebSearchProvider()

    def _get_tools(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_general_web",
                    "description": "Performs a standard web search using DuckDuckGo.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query (e.g., 'Tata Motors EV battery tax').",
                            },
                            "time_range": {
                                "type": "string",
                                "description": "Optional filter: 'd' (day), 'w' (week), 'm' (month), 'y' (year).",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_latest_news",
                    "description": "Searches only the News tab for breaking events.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The news topic.",
                            },
                            "time_range": {
                                "type": "string",
                                "description": "Default is 'w' (week).",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "scrape_webpage",
                    "description": "Extracts the raw text content from a specific URL. Use this if a search snippet is not enough.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The fully qualified URL to scrape.",
                            }
                        },
                        "required": ["url"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_research_report",
                    "description": "Submits the final research findings and citations.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "summary_of_findings": {
                                "type": "string",
                                "description": "A clear, professional summary of the research findings.",
                            },
                            "is_breaking_news_detected": {
                                "type": "boolean",
                                "description": "True if the research uncovered breaking news.",
                            },
                            "potential_market_impact": {
                                "type": "string",
                                "enum": ["Bullish", "Bearish", "Neutral"],
                                "description": "Estimated market impact.",
                            },
                            "citations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "url": {"type": "string"},
                                        "key_fact_extracted": {"type": "string"},
                                    },
                                    "required": ["title", "url", "key_fact_extracted"],
                                },
                                "description": "List of sources to prove findings.",
                            },
                        },
                        "required": [
                            "summary_of_findings",
                            "is_breaking_news_detected",
                            "potential_market_impact",
                            "citations",
                        ],
                    },
                },
            },
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Executes the web search tools."""
        try:
            if tool_name == "search_general_web":
                query = arguments.get("query", "")
                time_range = arguments.get("time_range")
                safe_time_range = WebSearchProvider.normalize_time_range(
                    str(time_range) if time_range else None,
                    default=None,
                )
                results = self.provider.search_general_web(
                    query, time_range=safe_time_range
                )
                return json.dumps(results)

            elif tool_name == "search_latest_news":
                query = arguments.get("query", "")
                time_range = arguments.get("time_range", "w")
                safe_time_range = WebSearchProvider.normalize_time_range(
                    str(time_range) if time_range else None,
                    default="w",
                )
                results = self.provider.search_latest_news(
                    query, time_range=safe_time_range
                )
                return json.dumps(results)

            elif tool_name == "scrape_webpage":
                url = arguments.get("url", "")
                result = self.provider.scrape_webpage(url)
                # Cap the length so it doesn't blow up the context window
                return json.dumps({"content": result[:8000]})

            elif tool_name == "submit_research_report":
                return json.dumps(arguments)

            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:WebSearch:Execute")
    async def execute(self, user_query: str, step_number: int = 0) -> AgentResponse:
        """
        Executes the agent loop using a robust, multi-turn tool-based architecture.
        """
        messages: List[Message] = [
            Message(
                role="system", content=prompt_manager.get_prompt("web_search.system")
            ),
            Message(
                role="user",
                content=prompt_manager.get_prompt(
                    "web_search.user_initial", user_query=user_query
                ),
            ),
        ]

        max_turns = 5
        current_turn = 0

        try:
            while current_turn < max_turns:
                response_msg = await self.llm_service.generate_message(
                    messages=messages, model=self.model, tools=self._get_tools()
                )

                if not response_msg.content:
                    response_msg.content = "Processing..."

                messages.append(response_msg)

                if response_msg.tool_calls:
                    for tool_call in response_msg.tool_calls:
                        function_call = tool_call.get("function", {})
                        tool_name = function_call.get("name")

                        arguments_str = function_call.get("arguments", "{}")
                        try:
                            arguments = (
                                json.loads(arguments_str)
                                if isinstance(arguments_str, str)
                                else arguments_str
                            )
                        except json.JSONDecodeError:
                            arguments = {}

                        # Check if it's the final submission tool
                        if tool_name == "submit_research_report":
                            final_data = self._execute_tool(tool_name, arguments)
                            return AgentResponse(
                                status="success",
                                data=json.loads(final_data),
                                errors=None,
                            )

                        # Otherwise, execute the search/scrape tool
                        tid = await self.emit_status(
                            step_number,
                            tool_name,
                            json.dumps(arguments),
                            status="running",
                        )
                        tool_result = self._execute_tool(tool_name, arguments)
                        await self.emit_status(
                            step_number,
                            tool_name,
                            json.dumps(arguments),
                            (
                                tool_result[:500] + "..."
                                if len(tool_result) > 500
                                else tool_result
                            ),
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
                    current_turn += 1
                else:
                    # If the LLM returns text without calling a tool, we treat it as the final content but flag it.
                    return AgentResponse(
                        status="success",
                        data={"response": response_msg.content},
                        errors=[
                            "Final output was text-only, not structured JSON via submit_research_report tool."
                        ],
                    )

            # If the loop finishes without a 'submit_research_report' call.
            return AgentResponse(
                status="failure",
                data={},
                errors=[f"Agent failed to submit results within {max_turns} turns."],
            )

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
