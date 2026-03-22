import json
from typing import Dict, Any
from app.core.observability import observe, langfuse_context

from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.retrieval.schemas import AgentResponse
from storage.vector.client import QdrantStorage
from app.services.embedding_service import EmbeddingService
from agents.base import BaseAgent


class RetrievalAgent(BaseAgent):
    """
    Agent responsible for translating user queries into vector embeddings,
    searching the Qdrant database for relevant textual context (like news),
    and synthesizing a response.
    """

    SYSTEM_PROMPT = """
You are the Retrieval (RAG) Agent for a Financial Intelligence Platform.
Your job is to search the intelligence database for text data (news, transcripts, reports) that answers the user's question.

CRITICAL RULES:
1. You DO NOT perform mathematical computations.
2. HYBRID SEARCH: Use the `search_intelligence_db` tool. It combines semantic meaning with keyword matching. Be specific with your search query.
3. TEMPORAL AWARENESS: Financial data changes fast. Prioritize recent information.
4. SYNTHESIS: Formulate your final answer using ONLY the context returned by the tool. Cite your sources if metadata is available.
5. If the context doesn't answer the question after retrying, explicitly state that you have "Insufficient Data" to provide a reliable answer.
6. Always respond with JSON matching the AgentResponse schema at the end.
    """

    def __init__(
        self,
        llm_service: LLMServiceInterface,
        qdrant_client: QdrantStorage,
        model: str = "mistral-8b",
    ):
        super().__init__(llm_service, model)
        self.db = qdrant_client
        self.embed_service = EmbeddingService()

    def _get_tools(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_intelligence_db",
                    "description": "Performs hybrid search (semantic + keyword) in the intelligence database for news and reports.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The specific question or semantic query. Be descriptive for better hybrid matching.",
                            },
                            "ticker": {
                                "type": "string",
                                "description": "Optional stock ticker to filter by (e.g., RELIANCE).",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of chunks to return (default 10).",
                            },
                        },
                        "required": ["query"],
                    },
                },
            }
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        try:
            if tool_name == "search_intelligence_db":
                query = arguments.get("query", "")
                ticker = arguments.get("ticker", None)
                limit = arguments.get("limit", 10)

                # 1. Embed the query
                query_vector = self.embed_service.embed_text(query)

                # 2. Search Qdrant with hybrid capabilities
                results = self.db.search(
                    query_embedding=query_vector,
                    query_text=query,
                    limit=limit,
                    ticker=ticker,
                )

                if not results:
                    return json.dumps(
                        {
                            "status": "no_results",
                            "message": "No relevant information found for the given query.",
                        }
                    )

                # 3. Format results
                formatted_results = []
                for chunk in results:
                    formatted_results.append(
                        {
                            "ticker": chunk.ticker,
                            "text": chunk.text,
                            "metadata": chunk.metadata,
                        }
                    )

                return json.dumps(formatted_results)

            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})

        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:Retrieval:Execute")
    async def execute(self, user_query: str, step_number: int = 0) -> AgentResponse:
        """
        Executes the agent loop with a self-correction retry if results are insufficient.
        """
        messages = [
            Message(role="system", content=self.SYSTEM_PROMPT),
            Message(role="user", content=user_query),
        ]

        try:
            # Attempt 1: Standard retrieval
            tid_gen = await self.emit_status(
                step_number, self.agent_name, "Generating search query...", status="running"
            )
            response_msg = await self.llm_service.generate_message(
                messages=messages, model=self.model, tools=self._get_tools()
            )
            await self.emit_status(
                step_number, self.agent_name, "Generating search query...", "Search query generated.", status="completed", tool_id=tid_gen
            )

            messages.append(response_msg)

            if response_msg.tool_calls:
                tool_call = response_msg.tool_calls[
                    0
                ]  # Usually just one search tool call
                function_call = tool_call.get("function", {})
                tool_name = function_call.get("name")

                raw_args = function_call.get("arguments", "{}")
                arguments = (
                    json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                )

                tid = await self.emit_status(
                    step_number, tool_name, json.dumps(arguments), status="running"
                )
                tool_result_str = self._execute_tool(tool_name, arguments)
                tool_result = json.loads(tool_result_str)
                await self.emit_status(
                    step_number,
                    tool_name,
                    json.dumps(arguments),
                    tool_result_str[:500] + "..." if len(tool_result_str) > 500 else tool_result_str,
                    status="completed",
                    tool_id=tid,
                )

                # SELF-CORRECTION: If no results, retry with a broader query
                if (
                    isinstance(tool_result, dict)
                    and tool_result.get("status") == "no_results"
                ):
                    langfuse_context.update_current_observation(
                        metadata={"retry": True, "reason": "no_results"}
                    )

                    retry_prompt = f"The previous search for '{arguments.get('query')}' yielded no results. Please try one more time with a broader or different search query that might find relevant financial context for: '{user_query}'"

                    messages.append(
                        Message(
                            role="tool",
                            content=tool_result_str,
                            name=tool_name,
                            tool_call_id=tool_call.get("id"),
                        )
                    )
                    messages.append(Message(role="user", content=retry_prompt))

                    tid_retry = await self.emit_status(
                        step_number, self.agent_name, "Retrying search with broader query...", status="running"
                    )
                    response_msg = await self.llm_service.generate_message(
                        messages=messages, model=self.model, tools=self._get_tools()
                    )
                    await self.emit_status(
                        step_number, self.agent_name, "Retrying search with broader query...", "Retry query generated.", status="completed", tool_id=tid_retry
                    )
                    messages.append(response_msg)

                    if response_msg.tool_calls:
                        tool_call = response_msg.tool_calls[0]
                        function_call = tool_call.get("function", {})
                        raw_args = function_call.get("arguments", "{}")
                        arguments = (
                            json.loads(raw_args)
                            if isinstance(raw_args, str)
                            else raw_args
                        )
                        
                        tid = await self.emit_status(
                            step_number, tool_call.get("function", {}).get("name"), json.dumps(arguments), status="running"
                        )
                        tool_result_str = self._execute_tool(
                            function_call.get("name"), arguments
                        )
                        await self.emit_status(
                            step_number,
                            tool_call.get("function", {}).get("name"),
                            json.dumps(arguments),
                            tool_result_str[:500] + "..." if len(tool_result_str) > 500 else tool_result_str,
                            status="completed",
                            tool_id=tid,
                        )

                messages.append(
                    Message(
                        role="tool",
                        content=tool_result_str,
                        name=tool_name,
                        tool_call_id=tool_call.get("id"),
                    )
                )

                # Final synthesis
                messages.append(
                    Message(
                        role="user",
                        content="The intelligence retrieval process is complete. Synthesize the findings into a clear answer. If no relevant data was found, state 'Insufficient Data'.",
                    )
                )

                tid_synth = await self.emit_status(
                    step_number, self.agent_name, "Synthesizing retrieved information...", status="running"
                )
                final_response_msg = await self.llm_service.generate_message(
                    messages=messages, model=self.model
                )
                await self.emit_status(
                    step_number, self.agent_name, "Synthesizing retrieved information...", "Synthesis complete.", status="completed", tool_id=tid_synth
                )
                final_content = final_response_msg.content
            else:
                final_content = response_msg.content

            return AgentResponse(
                status="success", data={"response": final_content}, errors=None
            )

        except Exception as e:
            # We could add an error status here if we have a tid
            return AgentResponse(status="failure", data={}, errors=[str(e)])
