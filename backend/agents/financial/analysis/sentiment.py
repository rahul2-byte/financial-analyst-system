"""Sentiment analysis graph node handler."""

import json
from typing import Any, Dict

from app.config import settings
from app.core.graph.graph_state import ResearchGraphState
from app.core.graph.node_helpers import build_node_error, build_node_success
from app.core.node_resources import NodeResources
from app.models.request_models import Message
from app.core.tools.tool_system import ToolNamespace, tool_executor, tool_registry
from app.config.constants import MODEL_REASONING


async def sentiment_analysis_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Uses LLM and Qdrant MCP for text RAG sentiment analysis."""
    current_step = state.get("current_step") or {}
    params = current_step.get("parameters", {})
    if not isinstance(params, dict):
        params = {}

    ticker = params.get("ticker", "UNKNOWN")
    query = params.get("query", "")

    # We provide the LLM with Qdrant MCP tools and ANALYSIS tools
    tools = [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tool_registry.get_tools_by_namespace(ToolNamespace.RESEARCH)
        + tool_registry.get_tools_by_namespace(ToolNamespace.ANALYSIS)
        if t.name in ["qdrant_search_vector_db", "submit_sentiment"]
    ]

    messages = [
        Message(
            role="system",
            content="You are a sentiment analyst. You must use the 'qdrant_search_vector_db' tool to fetch recent news, filings, and transcript data for the ticker from the vector database. Analyze the sentiment of the retrieved texts, and submit your findings using the 'submit_sentiment' tool.",
        ),
        Message(
            role="user",
            content=f"Please analyze the sentiment for {ticker}. User Query Context: {query}",
        ),
    ]

    final_result = None
    response = None

    try:
        for _ in range(5):
            response = await resources.llm_service.generate_message(
                messages=messages, model=MODEL_REASONING, tools=tools
            )
            messages.append(response)

            if not response.tool_calls:
                break

            for tool_call in response.tool_calls:
                func = tool_call.get("function", {})
                short_name = func.get("name")
                args = json.loads(func.get("arguments", "{}"))

                if short_name.startswith("qdrant_"):
                    full_name = f"mcp_qdrant:{short_name.split('qdrant_', 1)[1]}"
                else:
                    full_name = f"analysis:{short_name}"

                tool_result = await tool_executor.execute(full_name, args)

                result_content = json.dumps(
                    tool_result.error if not tool_result.success else tool_result.data,
                    ensure_ascii=True,
                    default=str,
                )

                if short_name == "submit_sentiment":
                    final_result = args
                    break

                messages.append(
                    Message(
                        role="tool",
                        content=result_content,
                        name=short_name,
                        tool_call_id=tool_call.get("id"),
                    )
                )

            if final_result:
                break

        if not final_result:
            final_content = response.content if response else "No analysis generated."
            final_result = {
                "sentiment": "neutral",
                "score": 0.5,
                "summary": final_content,
            }

        return build_node_success(
            agent_output_key="sentiment_analysis",
            agent_output=final_result,
            tool_name="analysis:submit_sentiment",
            input_parameters=params,
            tool_output=final_result,
        )
    except Exception as error:
        return build_node_error(error)
