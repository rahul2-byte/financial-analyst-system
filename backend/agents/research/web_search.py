import json
from typing import Dict, Any, Optional
from app.core.observability import observe, langfuse_context

from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.research.schemas import AgentResponse, WebResearchResult
from data.providers.web_search import WebSearchProvider
from app.core.utils import clean_json_string


class WebSearchAgent:
    """
    Agent responsible for browsing the internet dynamically using DuckDuckGo
    to answer highly specific, real-time, or niche contextual questions.
    """

    SYSTEM_PROMPT = """
You are the Deep Web Research Agent for a Financial Intelligence Platform.
Your job is to use the provided search tools to find highly specific, up-to-date information that standard financial APIs might miss.

CRITICAL RULES:
1. QUERY EXPANSION: If you don't know the answer, use your search tools. If the first search is bad, rewrite the query and search again.
2. CONTEXTUALIZE: For Indian markets, you might need to append "India" or "NSE" to your queries for better results.
3. ANTI-HALLUCINATION: You MUST base your final answer ONLY on the text returned by the search tools. You MUST extract exact URLs for the citations field.
4. Your final output must EXACTLY match the WebResearchResult JSON schema. Do not output anything outside of the JSON.
    """

    def __init__(
        self,
        llm_service: LLMServiceInterface,
        model: str = "mistral-8b",
        provider: Optional[WebSearchProvider] = None,
    ):
        self.llm = llm_service
        self.model = model
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
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Executes the web search tools."""
        try:
            if tool_name == "search_general_web":
                query = arguments.get("query", "")
                time_range = arguments.get("time_range")
                # Ensure time_range is a string if present, otherwise None
                results = self.provider.search_general_web(
                    query, time_range=str(time_range) if time_range else None
                )
                return json.dumps(results)

            elif tool_name == "search_latest_news":
                query = arguments.get("query", "")
                time_range = arguments.get("time_range", "w")
                # Ensure time_range is a string if present, otherwise None
                results = self.provider.search_latest_news(
                    query, time_range=str(time_range) if time_range else None
                )
                return json.dumps(results)

            elif tool_name == "scrape_webpage":
                url = arguments.get("url", "")
                result = self.provider.scrape_webpage(url)
                # Cap the length so it doesn't blow up the context window
                return json.dumps({"content": result[:8000]})

            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:WebSearch:Execute")
    async def execute(self, user_query: str) -> AgentResponse:
        """
        Executes the agent loop. Allows multiple tool calls in sequence if the LLM
        decides it needs to refine its search before giving a final answer.
        """
        messages = [
            Message(role="system", content=self.SYSTEM_PROMPT),
            Message(role="user", content=user_query),
        ]

        # We allow up to 3 turns for the agent to search, read, and search again
        max_turns = 3
        current_turn = 0

        try:
            while current_turn < max_turns:
                # In the last turn, or if we want to force JSON, we can pass response_format.
                # However, if the LLM wants to call a tool, it can't return structured JSON at the same time usually.
                response_msg = await self.llm.generate_message(
                    messages=messages, model=self.model, tools=self._get_tools()
                )

                if not response_msg.content:
                    response_msg.content = "Calling tool..."

                messages.append(response_msg)

                # If the LLM didn't call a tool, it thinks it's ready to answer.
                # We can break and then do one final pass for the structured JSON.
                if not response_msg.tool_calls:
                    break

                # Execute tools
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

                current_turn += 1

            # Now we have all the information in the messages history.
            # Perform the final synthesis step enforcing the JSON schema.
            if messages[-1].role == "tool":
                # Let the assistant process the tool results before we ask for the final JSON
                intermediate_msg = await self.llm.generate_message(
                    messages=messages, model=self.model
                )
                if not intermediate_msg.content:
                    intermediate_msg.content = "Processed tool results."
                messages.append(intermediate_msg)

            schema_str = json.dumps(WebResearchResult.model_json_schema())
            final_prompt = (
                f"Based on all the research findings above, synthesize the results into a final JSON object matching this schema: {schema_str}\n\n"
                "CRITICAL: You MUST return ONLY valid JSON. Do not wrap your response in markdown backticks (```json). "
                "Do not include any conversational text or explanations."
            )
            messages.append(Message(role="user", content=final_prompt))
            final_response_msg = await self.llm.generate_message(
                messages=messages,
                model=self.model,
                response_format={"type": "json_object"},
            )
            final_content = final_response_msg.content

            if not final_content:
                # If the LLM returned an empty string, maybe it was just a conversational response before.
                # But we forced JSON, so this is unlikely unless the model is failing.
                raise ValueError("LLM returned empty content for final synthesis.")

            try:
                # Ensure final_content is not None or empty before loading
                if not final_content:
                    raise ValueError("Final content from LLM is empty or None.")
                cleaned_content = clean_json_string(final_content)
                parsed_insights = json.loads(cleaned_content)
            except Exception as json_e:
                # Log the error for debugging
                import logging

                logging.getLogger(__name__).error(
                    f"Failed to parse LLM final content as JSON: {json_e}. Content: {final_content}"
                )
                parsed_insights = {
                    "raw_output": final_content,
                    "parse_error": str(json_e),
                }

            return AgentResponse(status="success", data=parsed_insights, errors=None)

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
