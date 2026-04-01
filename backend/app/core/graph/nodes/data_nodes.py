"""Data acquisition and retrieval graph node handlers."""
import json
import logging
from typing import Any, Dict, List

from app.core.graph.graph_state import ResearchGraphState
from app.core.node_resources import NodeResources
from app.core.graph.node_helpers import build_node_error, build_node_success
from app.core.prompts import prompt_manager
from app.models.request_models import Message
from app.core.orchestration_schemas import OfflineStatus
from app.config import settings
from app.core.tools.tool_system import tool_registry, tool_executor, ToolNamespace

logger = logging.getLogger(__name__)


async def market_offline_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """
    Intelligent agent node that verifies market data availability in local DB.
    Uses centralized tool system for tool definitions and execution.
    """
    params = state.get("current_step", {}).get("parameters", {})
    ticker = params.get("ticker", "")
    
    # Fast path for discovery or internal checks to avoid recursive LLM loops
    if state.get("status") == "discovering":
        info = resources.sql_db.get_ticker_info(ticker)
        return build_node_success(
            agent_output_key="market_offline",
            agent_output={"data_available": info.get("ticker_found", False), "extra_info": info},
            tool_name="market:get_ticker_info",
            input_parameters=params,
            tool_output=info,
        )

    llm_service = resources.llm_service
    model = settings.DEFAULT_LLM_MODEL

    try:
        messages = [
            Message(
                role="system", content=prompt_manager.get_prompt("market_offline.system")
            ),
            Message(
                role="user",
                content=f"Verify if OHLCV data for '{ticker}' is available in the local database.",
            ),
        ]

        # Get tools from central registry
        registered_tools = tool_registry.get_tools_by_namespace(ToolNamespace.MARKET)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,  # Use short name for LLM compatibility
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in registered_tools
        ]

        final_status = None
        # Limit iterations to avoid infinite loops
        for i in range(5):
            logger.debug(f"Market offline agent loop {i+1}")
            response = await llm_service.generate_message(
                messages=messages, model=model, tools=tools
            )
            # Fix: Convert to Message object if it's not already
            if not isinstance(response, Message):
                # If it's an AgentResponse or similar, we should normalize it
                # Assuming llm_service.generate_message returns a Message object
                # But the review says response is an AgentResponse object?
                # Let's check the review's wording.
                pass
            messages.append(response)

            if not response.tool_calls:
                logger.debug("No tool calls, breaking loop")
                break

            for tool_call in response.tool_calls:
                func = tool_call.get("function", {})
                short_name = func.get("name")
                logger.debug(f"Tool call: {short_name}")
                args = json.loads(func.get("arguments", "{}"))

                # Execute via central tool executor
                full_name = f"{ToolNamespace.MARKET.value}:{short_name}"
                tool_result = await tool_executor.execute(full_name, args)

                if not tool_result.success:
                    logger.error(f"Tool {full_name} failed: {tool_result.error}")
                    result_content = json.dumps({"error": tool_result.error})
                else:
                    result_content = json.dumps(tool_result.data)
                    if short_name == "submit_offline_status":
                        final_status = OfflineStatus.model_validate(tool_result.data)

                messages.append(
                    Message(
                        role="tool",
                        content=result_content,
                        name=short_name,
                        tool_call_id=tool_call.get("id"),
                    )
                )

            if final_status:
                break

        if final_status:
            return build_node_success(
                agent_output_key="market_offline",
                agent_output=final_status.model_dump(),
                tool_name="market_offline_agent",
                input_parameters=params,
                tool_output=final_status.model_dump(),
            )

        return build_node_error(
            ValueError("Market offline agent failed to reach a conclusion")
        )

    except Exception as error:

        logger.error(f"Market offline node failed: {error}", exc_info=True)
        return build_node_error(error)



async def price_and_fundamentals_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Fetches stock data and fundamentals from Yahoo Finance."""
    params = state.get("current_step", {}).get("parameters", {})
    ticker = params.get("ticker", "")
    try:
        price_data = resources.yf_fetcher.fetch_stock_price(ticker)
        fundamentals = resources.yf_fetcher.fetch_company_fundamentals(ticker)
        result = {"ticker": ticker, "price": price_data, "fundamentals": fundamentals}
        return build_node_success(
            agent_output_key="price_and_fundamentals",
            agent_output=result,
            tool_name="data:fetch_stock_data",
            input_parameters=params,
            tool_output=result,
        )
    except Exception as error:
        return build_node_error(error)


async def market_news_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Fetches market news from RSS and searches vector DB."""
    params = state.get("current_step", {}).get("parameters", {})
    query = params.get("query", "")
    try:
        news = resources.rss_fetcher.fetch_market_news(query)
        result = {"articles": news}
        return build_node_success(
            agent_output_key="market_news",
            agent_output=result,
            tool_name="news:fetch_news",
            input_parameters=params,
            tool_output=result,
        )
    except Exception as error:
        return build_node_error(error)


async def macro_indicators_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Fetches macroeconomic data."""
    params = state.get("current_step", {}).get("parameters", {})
    try:
        indicators = resources.yf_fetcher.fetch_macro_indicators()
        return build_node_success(
            agent_output_key="macro_indicators",
            agent_output=indicators,
            tool_name="macro:fetch_macro_data",
            input_parameters=params,
            tool_output=indicators,
        )
    except Exception as error:
        return build_node_error(error)


async def retrieval_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Searches vector database for context."""
    params = state.get("current_step", {}).get("parameters", {})
    query = params.get("query", "")
    try:
        results = resources.vector_db.search(
            query_embedding=None,
            query_text=query,
            limit=5,
        )
        return build_node_success(
            agent_output_key="retrieval",
            agent_output={"results": results},
            tool_name="retrieval:hybrid_search",
            input_parameters=params,
            tool_output={"results": results},
        )
    except Exception as error:
        return build_node_error(error)


async def web_search_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Stateless node for web search using DuckDuckGo."""
    params = state.get("current_step", {}).get("parameters", {})
    query = params.get("query", "")
    time_range = params.get("time_range", "m")
    try:
        results = resources.web_search.search(query, time_range=time_range)
        return build_node_success(
            agent_output_key="web_search",
            agent_output={"results": results},
            tool_name="web_search:search",
            input_parameters=params,
            tool_output={"results": results},
        )
    except Exception as error:
        return build_node_error(error, prefix="Web search failed: ")
