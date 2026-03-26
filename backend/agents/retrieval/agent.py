import json
from typing import Dict, Any, List, Optional
from app.core.observability import observe, langfuse_context

from app.core.prompts import prompt_manager
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
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_retrieval_results",
                    "description": "Submits the final synthesized answer based on retrieved context.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "answer": {
                                "type": "string",
                                "description": "The synthesized answer based on retrieved context.",
                            },
                            "sources": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "A list of sources (titles, dates, or tickers) cited from the context.",
                            },
                            "confidence": {
                                "type": "number",
                                "description": "A score from 0.0 to 1.0 indicating confidence in the answer.",
                            },
                            "insufficient_data": {
                                "type": "boolean",
                                "description": "True if no relevant context was found to answer the query.",
                            },
                        },
                        "required": ["answer", "confidence", "insufficient_data"],
                    },
                },
            },
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

            elif tool_name == "submit_retrieval_results":
                return json.dumps(arguments)

            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})

        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:Retrieval:Execute")
    async def execute(self, user_query: str, step_number: int = 0) -> AgentResponse:
        """
        Executes the retrieval loop.
        Translates query to vector, searches Qdrant, and synthesizes an answer via submission tool.
        """
        messages = [
            Message(
                role="system", content=prompt_manager.get_prompt("retrieval.system")
            ),
            Message(role="user", content=user_query),
        ]

        try:
            # First LLM call -> Should call search_intelligence_db
            response_msg = await self.llm_service.generate_message(
                messages=messages, model=self.model, tools=self._get_tools()
            )
            messages.append(response_msg)

            if response_msg.tool_calls:
                tool_call = response_msg.tool_calls[0]
                tool_name = tool_call.get("function", {}).get("name")

                if tool_name == "submit_retrieval_results":
                    arguments = json.loads(
                        tool_call.get("function", {}).get("arguments", "{}")
                    )
                    return AgentResponse(status="success", data=arguments, errors=None)

                arguments = json.loads(
                    tool_call.get("function", {}).get("arguments", "{}")
                )
                tool_result_str = self._execute_tool(tool_name, arguments)
                tool_result = json.loads(tool_result_str)

                # SELF-CORRECTION: If no results, retry once with a broader query
                if (
                    isinstance(tool_result, dict)
                    and tool_result.get("status") == "no_results"
                ):
                    messages.append(
                        Message(
                            role="tool",
                            content=tool_result_str,
                            name=tool_name,
                            tool_call_id=tool_call.get("id"),
                        )
                    )

                    retry_prompt = prompt_manager.get_prompt(
                        "retrieval.feedback",
                        query=arguments.get("query"),
                        user_query=user_query,
                    )
                    messages.append(Message(role="user", content=retry_prompt))

                    response_msg = await self.llm_service.generate_message(
                        messages=messages, model=self.model, tools=self._get_tools()
                    )
                    messages.append(response_msg)

                    if response_msg.tool_calls:
                        tool_call = response_msg.tool_calls[0]
                        tool_name = tool_call.get("function", {}).get("name")

                        if tool_name == "submit_retrieval_results":
                            arguments = json.loads(
                                tool_call.get("function", {}).get("arguments", "{}")
                            )
                            return AgentResponse(
                                status="success", data=arguments, errors=None
                            )

                        arguments = json.loads(
                            tool_call.get("function", {}).get("arguments", "{}")
                        )
                        tool_result_str = self._execute_tool(tool_name, arguments)

                messages.append(
                    Message(
                        role="tool",
                        content=tool_result_str,
                        name=tool_name,
                        tool_call_id=tool_call.get("id"),
                    )
                )

            # Final synthesis -> Must call submit_retrieval_results
            final_response_msg = await self.llm_service.generate_message(
                messages=messages, model=self.model, tools=self._get_tools()
            )

            if final_response_msg.tool_calls:
                final_tool_call = final_response_msg.tool_calls[0]
                if (
                    final_tool_call.get("function", {}).get("name")
                    == "submit_retrieval_results"
                ):
                    arguments = json.loads(
                        final_tool_call.get("function", {}).get("arguments", "{}")
                    )
                    return AgentResponse(status="success", data=arguments, errors=None)

            return AgentResponse(
                status="success",
                data={"response": final_response_msg.content},
                errors=[
                    "Agent failed to use the submit_retrieval_results tool on its final step."
                ],
            )

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
