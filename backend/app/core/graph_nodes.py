import asyncio
import json
import logging
from typing import List, Set, Dict, Any, Optional

from app.core.graph_state import ResearchGraphState
from app.core.prompts import prompt_manager
from app.core.agent_factories import LLMServiceFactory, DataServiceFactory
from app.services.llm_interface import LLMServiceInterface
from app.services.llama_cpp_service import LlamaCppService
from app.models.request_models import Message
from storage.sql.client import PostgresClient
from storage.vector.client import QdrantStorage
from data.providers.yfinance import YFinanceFetcher
from data.providers.rss_news import RSSNewsFetcher
from common.state import ToolResult

from app.core.orchestration_schemas import PlanData, ExecutionStep

# Import new stateless nodes
from app.core.nodes.planner_node import planner_node as planner_node_func
from app.core.nodes.verification_node import verification_node as verification_node_func
from app.core.nodes.validation_node import validation_node as validation_node_func

logger = logging.getLogger(__name__)


def _get_agent_name(step: ExecutionStep) -> str:
    """Extract agent name from step target."""
    if hasattr(step.target_agent, "value"):
        return step.target_agent.value
    return str(step.target_agent)


def _find_next_level(
    steps: List[ExecutionStep], executed_step_ids: Set[int]
) -> List[ExecutionStep]:
    """Find steps where all dependencies have been executed."""
    return [
        step
        for step in steps
        if all(dep in executed_step_ids for dep in step.dependencies)
    ]


async def planner_node(state: ResearchGraphState) -> Dict[str, Any]:
    """Stateless planner node - delegates to pure function."""
    return await planner_node_func(state)


async def execute_level_node(state: ResearchGraphState) -> Dict[str, Any]:
    """Executes the next level of steps in parallel using stateless function nodes."""

    # Map agent names to stateless function nodes (NEW architecture)
    agent_node_map = {
        "market_offline": market_offline_node,
        "market_online": price_and_fundamentals_node,  # Alias for price_and_fundamentals
        "price_and_fundamentals": price_and_fundamentals_node,
        "market_news": market_news_node,
        "macro_indicators": macro_indicators_node,
        "retrieval": retrieval_node,
        "web_search": web_search_node,  # Web search capability
        "fundamental_analysis": fundamental_analysis_node,
        "sentiment_analysis": sentiment_analysis_node,
        "macro_analysis": macro_analysis_node,
        "technical_analysis": technical_analysis_node,
        "contrarian_analysis": contrarian_analysis_node,
    }

    plan_data = state.get("plan")
    if not plan_data:
        return {"errors": ["No plan in state"]}

    if isinstance(plan_data, dict):
        execution_steps = plan_data.get("execution_steps", [])
        execution_steps = [ExecutionStep(**s) for s in execution_steps]
    else:
        execution_steps = plan_data.execution_steps

    current_executed = state.get("executed_steps", [])
    executed_step_ids = {
        s.get("step_number", s.step_number if hasattr(s, "step_number") else -1)
        for s in current_executed
    }

    next_level = _find_next_level(execution_steps, executed_step_ids)

    if not next_level:
        if len(current_executed) < len(execution_steps):
            return {
                "errors": ["No steps ready to execute - possible circular dependency"]
            }
        return {
            "agent_outputs": state.get("agent_outputs", {}),
            "executed_steps": current_executed,
        }

    agent_tasks = []
    for step in next_level:
        agent_name = _get_agent_name(step)

        # Get the stateless function node
        node_func = agent_node_map.get(agent_name)

        if not node_func:
            logger.error(f"Agent {agent_name} not found in node map")
            return {"errors": [f"Agent {agent_name} not found"]}

        # Create a modified state with current step info
        modified_state = {**state, "current_step": step.model_dump()}
        agent_tasks.append(node_func(modified_state))

    if agent_tasks:
        results = await asyncio.gather(*agent_tasks, return_exceptions=True)
    else:
        results = []

    new_agent_outputs = dict(state.get("agent_outputs", {}))
    new_executed_steps = list(current_executed)

    for step, result in zip(next_level, results):
        agent_name = _get_agent_name(step)
        new_tool_results = []

        if isinstance(result, Exception):
            logger.error(f"Step {step.step_number} failed: {result}")
            new_agent_outputs[str(step.step_number)] = f"Error: {str(result)}"
        else:
            # Check if result is from new node function or legacy agent
            if isinstance(result, dict) and "agent_outputs" in result:
                # New node function result
                new_agent_outputs[str(step.step_number)] = result.get(
                    "agent_outputs", {}
                ).get(agent_name, "")
                new_tool_results = result.get("tool_registry", [])
            else:
                # Legacy agent result
                new_agent_outputs[str(step.step_number)] = result.get("output", "")

        new_executed_steps.append(
            {"step_number": step.step_number, "agent": agent_name}
        )

    return {
        "agent_outputs": new_agent_outputs,
        "executed_steps": new_executed_steps,
        "tool_registry": new_tool_results,  # Will be merged via reducer
    }


async def synthesis_node(state: ResearchGraphState) -> Dict[str, Any]:
    """Generates draft report from agent outputs using LLM."""
    llm = LLMServiceFactory.get_llm_service()
    sql_db = DataServiceFactory.get_sql_db()
    vector_db = DataServiceFactory.get_vector_db()
    yf_fetcher = DataServiceFactory.get_yf_fetcher()
    rss_fetcher = DataServiceFactory.get_rss_fetcher()
    user_query = state["user_query"]
    agent_outputs = state.get("agent_outputs", {})

    synthesis_retry_count = state.get("synthesis_retry_count", 0)
    verification_feedback = state.get("verification_feedback", "")

    logger.info(
        f"Synthesis node generating draft report (attempt {synthesis_retry_count + 1})"
    )

    try:
        prompt_header = prompt_manager.get_prompt(
            "orchestrator.synthesis.header", user_query=user_query
        )

        agent_output_sections = []
        for step_num, output in agent_outputs.items():
            section_header = prompt_manager.get_prompt(
                "orchestrator.synthesis.section_header", section_name=f"Step {step_num}"
            )
            agent_output_sections.append(f"{section_header}\n{output}")

        prompt = prompt_header + "\n\n" + "\n\n".join(agent_output_sections)
        
        # Add verification feedback if this is a retry
        if verification_feedback:
            feedback_prompt = prompt_manager.get_prompt(
                "orchestrator.synthesis.feedback", error=verification_feedback
            )
            prompt += "\n\n" + feedback_prompt
        
        prompt += prompt_manager.get_prompt("orchestrator.synthesis.instructions")

        response = await llm.generate_message(
            messages=[Message(role="user", content=prompt)],
            model="mistral-8b",
        )

        draft_report = response.content if response.content else ""

        if not draft_report:
            return {
                "draft_report": None,
                "errors": ["Synthesis failed to generate draft report"],
                "synthesis_retry_count": synthesis_retry_count + 1,
            }

        return {
            "draft_report": draft_report,
            "synthesis_retry_count": synthesis_retry_count + 1,
        }

    except Exception as e:
        logger.error(f"Synthesis node error: {e}", exc_info=True)
        return {
            "draft_report": None,
            "errors": [f"Synthesis error: {str(e)}"],
            "synthesis_retry_count": synthesis_retry_count + 1,
        }


async def verification_node(state: ResearchGraphState) -> Dict[str, Any]:
    """Stateless verification node - delegates to pure function."""
    return await verification_node_func(state)


async def validation_node(state: ResearchGraphState) -> Dict[str, Any]:
    """Stateless validation node - delegates to pure function."""
    return await validation_node_func(state)


# ==================== STATELESS AGENT NODES ====================
# These replace the class-based agents with pure function nodes


async def market_offline_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for MarketOffline agent.
    Queries local PostgreSQL database for market data availability.
    """
    llm = LLMServiceFactory.get_llm_service()
    sql_db = DataServiceFactory.get_sql_db()
    vector_db = DataServiceFactory.get_vector_db()
    yf_fetcher = DataServiceFactory.get_yf_fetcher()
    rss_fetcher = DataServiceFactory.get_rss_fetcher()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    ticker = params.get("ticker", "")

    try:
        info = sql_db.get_ticker_info(ticker)
        tool_result = ToolResult(
            tool_name="market:get_ticker_info",
            input_parameters=params,
            output_data=info,
            extracted_metrics={},
        )
        tool_result.auto_extract_metrics()
        return {
            "agent_outputs": {"market_offline": json.dumps(info)},
            "tool_registry": [
                {
                    "tool_name": "market:get_ticker_info",
                    "input_parameters": params,
                    "output_data": info,
                    "extracted_metrics": tool_result.extracted_metrics,
                }
            ],
        }
    except Exception as e:
        logger.error(f"MarketOffline node error: {e}")
        return {"errors": [str(e)]}


async def price_and_fundamentals_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for PriceAndFundamentals agent.
    Fetches stock data and fundamentals from Yahoo Finance.
    """
    llm = LLMServiceFactory.get_llm_service()
    sql_db = DataServiceFactory.get_sql_db()
    vector_db = DataServiceFactory.get_vector_db()
    yf_fetcher = DataServiceFactory.get_yf_fetcher()
    rss_fetcher = DataServiceFactory.get_rss_fetcher()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    ticker = params.get("ticker", "")

    try:
        price_data = yf_fetcher.fetch_stock_price(ticker)
        fundamentals = yf_fetcher.fetch_company_fundamentals(ticker)

        result = {"ticker": ticker, "price": price_data, "fundamentals": fundamentals}

        tool_result = ToolResult(
            tool_name="data:fetch_stock_data",
            input_parameters=params,
            output_data=result,
            extracted_metrics={},
        )
        tool_result.auto_extract_metrics()
        return {
            "agent_outputs": {"price_and_fundamentals": json.dumps(result)},
            "tool_registry": [
                {
                    "tool_name": "data:fetch_stock_data",
                    "input_parameters": params,
                    "output_data": result,
                    "extracted_metrics": tool_result.extracted_metrics,
                }
            ],
        }
    except Exception as e:
        logger.error(f"PriceAndFundamentals node error: {e}")
        return {"errors": [str(e)]}


async def market_news_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for MarketNews agent.
    Fetches market news from RSS and searches vector DB.
    """
    llm = LLMServiceFactory.get_llm_service()
    sql_db = DataServiceFactory.get_sql_db()
    vector_db = DataServiceFactory.get_vector_db()
    yf_fetcher = DataServiceFactory.get_yf_fetcher()
    rss_fetcher = DataServiceFactory.get_rss_fetcher()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    query = params.get("query", "")

    try:
        news = rss_fetcher.fetch_market_news(query)

        tool_result = ToolResult(
            tool_name="news:fetch_news",
            input_parameters=params,
            output_data={"articles": news},
            extracted_metrics={},
        )
        tool_result.auto_extract_metrics()
        return {
            "agent_outputs": {"market_news": json.dumps({"articles": news})},
            "tool_registry": [
                {
                    "tool_name": "news:fetch_news",
                    "input_parameters": params,
                    "output_data": {"articles": news},
                    "extracted_metrics": tool_result.extracted_metrics,
                }
            ],
        }
    except Exception as e:
        logger.error(f"MarketNews node error: {e}")
        return {"errors": [str(e)]}


async def macro_indicators_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for MacroIndicators agent.
    Fetches macroeconomic data.
    """
    llm = LLMServiceFactory.get_llm_service()
    sql_db = DataServiceFactory.get_sql_db()
    vector_db = DataServiceFactory.get_vector_db()
    yf_fetcher = DataServiceFactory.get_yf_fetcher()
    rss_fetcher = DataServiceFactory.get_rss_fetcher()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})

    try:
        indicators = yf_fetcher.fetch_macro_indicators()

        tool_result = ToolResult(
            tool_name="macro:fetch_macro_data",
            input_parameters=params,
            output_data=indicators,
            extracted_metrics={},
        )
        tool_result.auto_extract_metrics()
        return {
            "agent_outputs": {"macro_indicators": json.dumps(indicators)},
            "tool_registry": [
                {
                    "tool_name": "macro:fetch_macro_data",
                    "input_parameters": params,
                    "output_data": indicators,
                    "extracted_metrics": tool_result.extracted_metrics,
                }
            ],
        }
    except Exception as e:
        logger.error(f"MacroIndicators node error: {e}")
        return {"errors": [str(e)]}


async def fundamental_analysis_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for FundamentalAnalysis agent.
    Uses FundamentalScanner for deterministic analysis.
    """
    llm = LLMServiceFactory.get_llm_service()
    sql_db = DataServiceFactory.get_sql_db()
    vector_db = DataServiceFactory.get_vector_db()
    yf_fetcher = DataServiceFactory.get_yf_fetcher()
    rss_fetcher = DataServiceFactory.get_rss_fetcher()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    raw_data = params.get("raw_data", {})

    try:
        from quant.fundamentals import FundamentalScanner

        scanner = FundamentalScanner()
        scan_results = scanner.scan(raw_data)

        tool_result = ToolResult(
            tool_name="analysis:run_fundamental_scan",
            input_parameters=params,
            output_data=scan_results,
            extracted_metrics={},
        )
        tool_result.auto_extract_metrics()
        return {
            "agent_outputs": {"fundamental_analysis": json.dumps(scan_results)},
            "tool_registry": [
                {
                    "tool_name": "analysis:run_fundamental_scan",
                    "input_parameters": params,
                    "output_data": scan_results,
                    "extracted_metrics": tool_result.extracted_metrics,
                }
            ],
        }
    except Exception as e:
        logger.error(f"FundamentalAnalysis node error: {e}")
        return {"errors": [str(e)]}


async def technical_analysis_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for TechnicalAnalysis agent.
    Uses TechnicalScanner for indicator calculations.
    """
    llm = LLMServiceFactory.get_llm_service()
    sql_db = DataServiceFactory.get_sql_db()
    vector_db = DataServiceFactory.get_vector_db()
    yf_fetcher = DataServiceFactory.get_yf_fetcher()
    rss_fetcher = DataServiceFactory.get_rss_fetcher()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    ohlcv_data = params.get("ohlcv_data", [])

    try:
        import pandas as pd
        from quant.indicators import TechnicalScanner

        df = pd.DataFrame(ohlcv_data)
        scanner = TechnicalScanner()
        scan_results = scanner.scan(df)

        tool_result = ToolResult(
            tool_name="analysis:run_technical_scan",
            input_parameters=params,
            output_data=scan_results,
            extracted_metrics={},
        )
        tool_result.auto_extract_metrics()
        return {
            "agent_outputs": {"technical_analysis": json.dumps(scan_results)},
            "tool_registry": [
                {
                    "tool_name": "analysis:run_technical_scan",
                    "input_parameters": params,
                    "output_data": scan_results,
                    "extracted_metrics": tool_result.extracted_metrics,
                }
            ],
        }
    except Exception as e:
        logger.error(f"TechnicalAnalysis node error: {e}")
        return {"errors": [str(e)]}


async def sentiment_analysis_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for SentimentAnalysis agent.
    Uses LLM for sentiment analysis.
    """
    llm = LLMServiceFactory.get_llm_service()
    sql_db = DataServiceFactory.get_sql_db()
    vector_db = DataServiceFactory.get_vector_db()
    yf_fetcher = DataServiceFactory.get_yf_fetcher()
    rss_fetcher = DataServiceFactory.get_rss_fetcher()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    text = params.get("text", "")

    try:
        prompt = f"Analyze the sentiment of this text: {text}"
        response = await llm.generate_message(
            messages=[Message(role="user", content=prompt)], model="mistral-8b"
        )

        result = {"text": text, "analysis": response.content}

        tool_result = ToolResult(
            tool_name="analysis:analyze_sentiment",
            input_parameters=params,
            output_data=result,
            extracted_metrics={},
        )
        tool_result.auto_extract_metrics()
        return {
            "agent_outputs": {"sentiment_analysis": json.dumps(result)},
            "tool_registry": [
                {
                    "tool_name": "analysis:analyze_sentiment",
                    "input_parameters": params,
                    "output_data": result,
                    "extracted_metrics": tool_result.extracted_metrics,
                }
            ],
        }
    except Exception as e:
        logger.error(f"SentimentAnalysis node error: {e}")
        return {"errors": [str(e)]}


async def macro_analysis_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for MacroAnalysis agent.
    Analyzes macroeconomic trends.
    """
    llm = LLMServiceFactory.get_llm_service()
    sql_db = DataServiceFactory.get_sql_db()
    vector_db = DataServiceFactory.get_vector_db()
    yf_fetcher = DataServiceFactory.get_yf_fetcher()
    rss_fetcher = DataServiceFactory.get_rss_fetcher()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    macro_data = params.get("macro_data", {})

    try:
        prompt = f"Analyze these macroeconomic indicators: {json.dumps(macro_data)}"
        response = await llm.generate_message(
            messages=[Message(role="user", content=prompt)], model="mistral-8b"
        )

        result = {"macro_data": macro_data, "analysis": response.content}

        tool_result = ToolResult(
            tool_name="analysis:analyze_macro",
            input_parameters=params,
            output_data=result,
            extracted_metrics={},
        )
        tool_result.auto_extract_metrics()
        return {
            "agent_outputs": {"macro_analysis": json.dumps(result)},
            "tool_registry": [
                {
                    "tool_name": "analysis:analyze_macro",
                    "input_parameters": params,
                    "output_data": result,
                    "extracted_metrics": tool_result.extracted_metrics,
                }
            ],
        }
    except Exception as e:
        logger.error(f"MacroAnalysis node error: {e}")
        return {"errors": [str(e)]}


async def contrarian_analysis_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for ContrarianAnalysis agent.
    Generates contrarian investment signals.
    """
    llm = LLMServiceFactory.get_llm_service()
    sql_db = DataServiceFactory.get_sql_db()
    vector_db = DataServiceFactory.get_vector_db()
    yf_fetcher = DataServiceFactory.get_yf_fetcher()
    rss_fetcher = DataServiceFactory.get_rss_fetcher()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    market_data = params.get("market_data", {})
    sentiment_data = params.get("sentiment_data", {})

    try:
        prompt = f"Provide a contrarian analysis based on: Market Data: {json.dumps(market_data)}, Sentiment: {json.dumps(sentiment_data)}"
        response = await llm.generate_message(
            messages=[Message(role="user", content=prompt)], model="mistral-8b"
        )

        result = {
            "market_data": market_data,
            "sentiment": sentiment_data,
            "analysis": response.content,
        }

        tool_result = ToolResult(
            tool_name="analysis:analyze_contrarian",
            input_parameters=params,
            output_data=result,
            extracted_metrics={},
        )
        tool_result.auto_extract_metrics()
        return {
            "agent_outputs": {"contrarian_analysis": json.dumps(result)},
            "tool_registry": [
                {
                    "tool_name": "analysis:analyze_contrarian",
                    "input_parameters": params,
                    "output_data": result,
                    "extracted_metrics": tool_result.extracted_metrics,
                }
            ],
        }
    except Exception as e:
        logger.error(f"ContrarianAnalysis node error: {e}")
        return {"errors": [str(e)]}


async def retrieval_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for Retrieval agent.
    Searches vector database for context.
    """
    llm = LLMServiceFactory.get_llm_service()
    sql_db = DataServiceFactory.get_sql_db()
    vector_db = DataServiceFactory.get_vector_db()
    yf_fetcher = DataServiceFactory.get_yf_fetcher()
    rss_fetcher = DataServiceFactory.get_rss_fetcher()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    query = params.get("query", "")

    try:
        results = vector_db.hybrid_search(query, limit=5)

        tool_result = ToolResult(
            tool_name="retrieval:hybrid_search",
            input_parameters=params,
            output_data={"results": results},
            extracted_metrics={},
        )
        tool_result.auto_extract_metrics()
        return {
            "agent_outputs": {"retrieval": json.dumps({"results": results})},
            "tool_registry": [
                {
                    "tool_name": "retrieval:hybrid_search",
                    "input_parameters": params,
                    "output_data": {"results": results},
                    "extracted_metrics": tool_result.extracted_metrics,
                }
            ],
        }
    except Exception as e:
        logger.error(f"Retrieval node error: {e}")
        return {"errors": [str(e)]}


async def web_search_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for web search using DuckDuckGo.
    """
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    query = params.get("query", "")
    time_range = params.get("time_range", "m")

    try:
        from data.providers.web_search import WebSearchProvider
        
        provider = WebSearchProvider()
        results = provider.search(query, time_range=time_range)
        
        tool_result = ToolResult(
            tool_name="web_search:search",
            input_parameters=params,
            output_data={"results": results},
            extracted_metrics={},
        )
        tool_result.auto_extract_metrics()
        
        return {
            "agent_outputs": {"web_search": json.dumps({"results": results})},
            "tool_registry": [
                {
                    "tool_name": tool_result.tool_name,
                    "input_parameters": tool_result.input_parameters,
                    "output_data": tool_result.output_data,
                    "extracted_metrics": tool_result.extracted_metrics,
                }
            ],
        }
    except Exception as e:
        logger.error(f"Web search node error: {e}")
        return {"errors": [f"Web search failed: {str(e)}"]}
