import asyncio
import json
import logging
from typing import List, Set, Dict, Any, Optional

from app.core.graph_state import ResearchGraphState
from app.core.prompts import prompt_manager
from app.services.llm_interface import LLMServiceInterface
from app.services.llama_cpp_service import LlamaCppService
from app.models.request_models import Message
from storage.sql.client import PostgresClient
from storage.vector.client import QdrantStorage
from data.providers.yfinance import YFinanceFetcher
from data.providers.rss_news import RSSNewsFetcher
from common.state import ToolResult

from agents.base import BaseAgent
from agents.orchestration.planner import PlannerAgent
from agents.orchestration.schemas import PlanData, ExecutionStep
from agents.data_access.market_offline import MarketOfflineAgent
from agents.data_access.price_and_fundamentals import PriceAndFundamentalsAgent
from agents.data_access.market_news import MarketNewsAgent
from agents.data_access.macro_indicators import MacroIndicatorsAgent
from agents.retrieval.agent import RetrievalAgent
from agents.analysis.fundamental import FundamentalAnalysisAgent
from agents.analysis.sentiment import SentimentAnalysisAgent
from agents.analysis.macro import MacroAnalysisAgent
from agents.analysis.technical import TechnicalAnalysisAgent
from agents.analysis.contrarian import ContrarianAgent
from agents.quality_control.verification import VerificationAgent
from agents.quality_control.validation import ValidationAgent
from agents.data_access.schemas import AgentResponse

logger = logging.getLogger(__name__)


class NodeResources:
    """Singleton for shared resources across graph nodes."""
    _instance = None
    
    llm: LlamaCppService
    sql_db: PostgresClient
    vector_db: QdrantStorage
    yf_fetcher: YFinanceFetcher
    rss_fetcher: RSSNewsFetcher

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(NodeResources, cls).__new__(cls)
            cls._instance.llm = LlamaCppService()
            cls._instance.sql_db = PostgresClient()
            cls._instance.vector_db = QdrantStorage()
            cls._instance.yf_fetcher = YFinanceFetcher()
            cls._instance.rss_fetcher = RSSNewsFetcher()
        return cls._instance


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
    """Wraps PlannerAgent to generate execution plan from user query."""
    llm = LlamaCppService()
    planner = PlannerAgent(llm_service=llm)

    user_query = state["user_query"]
    conversation_history = state.get("conversation_history", [])

    logger.info(f"Planner node processing query: {user_query}")
    response = await planner.execute(user_query)

    if response.status == "failure" or not response.data:
        logger.error(f"Planner failed: {response.errors}")
        return {"plan": None, "errors": [f"Planning failed: {response.errors}"]}

    plan_data = (
        response.data
        if isinstance(response.data, PlanData)
        else PlanData(**response.data)
    )

    logger.info(f"Planner generated {len(plan_data.execution_steps)} steps")

    return {
        "plan": (
            plan_data.model_dump() if hasattr(plan_data, "model_dump") else plan_data
        ),
    }


async def execute_level_node(state: ResearchGraphState) -> Dict[str, Any]:
    """Executes the next level of steps in parallel where dependencies are met."""
    llm = LlamaCppService()
    sql_db = PostgresClient()
    vector_db = QdrantStorage()
    yf_fetcher = YFinanceFetcher()
    rss_fetcher = RSSNewsFetcher()

    agent_map: Dict[str, BaseAgent] = {
        "market_offline": MarketOfflineAgent(llm_service=llm, db_client=sql_db),
        "price_and_fundamentals": PriceAndFundamentalsAgent(
            llm_service=llm, yf_fetcher=yf_fetcher, sql_db=sql_db
        ),
        "market_news": MarketNewsAgent(
            llm_service=llm, rss_fetcher=rss_fetcher, vector_db=vector_db
        ),
        "macro_indicators": MacroIndicatorsAgent(
            llm_service=llm, yf_fetcher=yf_fetcher, sql_db=sql_db
        ),
        "retrieval": RetrievalAgent(llm_service=llm, qdrant_client=vector_db),
        "fundamental_analysis": FundamentalAnalysisAgent(llm_service=llm),
        "sentiment_analysis": SentimentAnalysisAgent(llm_service=llm),
        "macro_analysis": MacroAnalysisAgent(llm_service=llm),
        "technical_analysis": TechnicalAnalysisAgent(llm_service=llm),
        "contrarian_analysis": ContrarianAgent(llm_service=llm),
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
        agent = agent_map.get(agent_name)
        if not agent:
            logger.error(f"Agent {agent_name} not found in agent map")
            return {"errors": [f"Agent {agent_name} not found"]}

        user_query = state["user_query"]
        context_from_prev = "\n".join(
            f"Step {s}: {state.get('agent_outputs', {}).get(str(s), '')}"
            for s in step.dependencies
            if str(s) in state.get("agent_outputs", {})
        )

        agent_query = f"Original Query: '{user_query}'\nAction: {step.action}\nParameters: {step.parameters}"
        if context_from_prev:
            agent_query += f"\n\nContext from previous steps:\n{context_from_prev}"

        agent_tasks.append(_execute_single_step(agent, agent_query, step))

    if agent_tasks:
        results = await asyncio.gather(*agent_tasks, return_exceptions=True)
    else:
        results = []

    new_agent_outputs = dict(state.get("agent_outputs", {}))
    new_executed_steps = list(current_executed)

    for step, result in zip(next_level, results):
        agent_name = _get_agent_name(step)
        if isinstance(result, Exception):
            logger.error(f"Step {step.step_number} failed: {result}")
            new_agent_outputs[str(step.step_number)] = f"Error: {str(result)}"
        else:
            new_agent_outputs[str(step.step_number)] = result.get("output", "")

        new_executed_steps.append(
            {"step_number": step.step_number, "agent": agent_name}
        )

    return {
        "agent_outputs": new_agent_outputs,
        "executed_steps": new_executed_steps,
    }


async def _execute_single_step(
    agent: BaseAgent, query: str, step: ExecutionStep
) -> Dict[str, Any]:
    """Executes a single agent step and returns output."""
    try:
        result = await agent.execute(query, step_number=step.step_number)
        if result.status == "success":
            output = ""
            if isinstance(result.data, dict) and "response" in result.data:
                output = result.data["response"]
            elif isinstance(result.data, dict):
                output = json.dumps(result.data)
            else:
                output = str(result.data)
            return {"output": output, "data": result.data}
        else:
            return {"output": f"Error: {result.errors}", "data": None}
    except Exception as e:
        return {"output": f"Exception: {str(e)}", "data": None}


async def synthesis_node(state: ResearchGraphState) -> Dict[str, Any]:
    """Generates draft report from agent outputs using LLM."""
    llm = LlamaCppService()
    user_query = state["user_query"]
    agent_outputs = state.get("agent_outputs", {})

    synthesis_retry_count = state.get("synthesis_retry_count", 0)

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
                "orchestrator.synthesis.section_header", step_number=step_num
            )
            agent_output_sections.append(f"{section_header}\n{output}")

        prompt = prompt_header + "\n\n" + "\n\n".join(agent_output_sections)
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
    """Verifies numeric accuracy of draft report using VerificationAgent."""
    llm = LlamaCppService()
    verifier = VerificationAgent(llm_service=llm)

    draft_report = state.get("draft_report") or ""
    tool_registry_raw = state.get("tool_registry", [])
    tool_registry: List[ToolResult] = [
        ToolResult(**t) if isinstance(t, dict) else t for t in tool_registry_raw
    ]

    logger.info("Verification node checking numeric accuracy")

    try:
        response = await verifier.execute(
            user_query="",
            step_number=0,
            draft_report=draft_report,
            tool_registry=tool_registry,
        )

        if response.status == "failure":
            logger.error(f"Verification failed: {response.errors}")
            return {
                "errors": [f"Verification error: {response.errors}"],
            }

        result_data = response.data if response.data else {}
        is_valid = result_data.get("is_valid", False)
        feedback = result_data.get("feedback", "")

        if is_valid:
            logger.info("Verification passed")
            return {"verification_passed": True}
        else:
            logger.warning(f"Verification failed: {feedback}")
            current_retry = state.get("verification_retry_count", 0)
            return {
                "verification_passed": False,
                "verification_retry_count": current_retry + 1,
                "errors": [feedback],
            }

    except Exception as e:
        logger.error(f"Verification node error: {e}", exc_info=True)
        return {
            "verification_passed": False,
            "errors": [f"Verification error: {str(e)}"],
        }


async def validation_node(state: ResearchGraphState) -> Dict[str, Any]:
    """Validates draft report for compliance using ValidationAgent."""
    llm = LlamaCppService()
    validator = ValidationAgent(llm_service=llm)

    user_query = state["user_query"]
    draft_report = state.get("draft_report") or ""

    logger.info("Validation node checking compliance")

    try:
        response = await validator.execute(
            user_query=user_query,
            step_number=0,
            draft_report=draft_report,
        )

        if response.status == "failure":
            logger.error(f"Validation failed: {response.errors}")
            return {
                "final_report": None,
                "errors": [f"Validation error: {response.errors}"],
            }

        result_data = response.data if response.data else {}
        is_valid = result_data.get("is_valid", False)
        final_approved_text = result_data.get("final_approved_text", "")

        if is_valid and final_approved_text:
            logger.info("Validation passed, final report approved")
            return {
                "final_report": final_approved_text,
            }
        else:
            violations = result_data.get("violations_found", [])
            logger.warning(f"Validation failed: {violations}")
            return {
                "final_report": None,
                "errors": [f"Validation violations: {violations}"],
            }

    except Exception as e:
        logger.error(f"Validation node error: {e}", exc_info=True)
        return {
            "final_report": None,
            "errors": [f"Validation error: {str(e)}"],
        }


# ==================== STATELESS AGENT NODES ====================
# These replace the class-based agents with pure function nodes


async def market_offline_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for MarketOffline agent.
    Queries local PostgreSQL database for market data availability.
    """
    resources = NodeResources()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    ticker = params.get("ticker", "")
    
    try:
        info = resources.sql_db.get_ticker_info(ticker)
        return {
            "agent_outputs": {"market_offline": json.dumps(info)},
            "tool_registry": [{
                "tool_name": "market:get_ticker_info",
                "input_parameters": params,
                "output_data": info,
                "extracted_metrics": {}
            }]
        }
    except Exception as e:
        logger.error(f"MarketOffline node error: {e}")
        return {"errors": [str(e)]}


async def price_and_fundamentals_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for PriceAndFundamentals agent.
    Fetches stock data and fundamentals from Yahoo Finance.
    """
    resources = NodeResources()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    ticker = params.get("ticker", "")
    
    try:
        price_data = resources.yf_fetcher.fetch_stock_price(ticker)
        fundamentals = resources.yf_fetcher.fetch_company_fundamentals(ticker)
        
        result = {
            "ticker": ticker,
            "price": price_data,
            "fundamentals": fundamentals
        }
        
        return {
            "agent_outputs": {"price_and_fundamentals": json.dumps(result)},
            "tool_registry": [{
                "tool_name": "data:fetch_stock_data",
                "input_parameters": params,
                "output_data": result,
                "extracted_metrics": {}
            }]
        }
    except Exception as e:
        logger.error(f"PriceAndFundamentals node error: {e}")
        return {"errors": [str(e)]}


async def market_news_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for MarketNews agent.
    Fetches market news from RSS and searches vector DB.
    """
    resources = NodeResources()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    query = params.get("query", "")
    
    try:
        news = resources.rss_fetcher.fetch_market_news(query)
        
        return {
            "agent_outputs": {"market_news": json.dumps({"articles": news})},
            "tool_registry": [{
                "tool_name": "news:fetch_news",
                "input_parameters": params,
                "output_data": {"articles": news},
                "extracted_metrics": {}
            }]
        }
    except Exception as e:
        logger.error(f"MarketNews node error: {e}")
        return {"errors": [str(e)]}


async def macro_indicators_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for MacroIndicators agent.
    Fetches macroeconomic data.
    """
    resources = NodeResources()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    
    try:
        indicators = resources.yf_fetcher.fetch_macro_indicators()
        
        return {
            "agent_outputs": {"macro_indicators": json.dumps(indicators)},
            "tool_registry": [{
                "tool_name": "macro:fetch_macro_data",
                "input_parameters": params,
                "output_data": indicators,
                "extracted_metrics": {}
            }]
        }
    except Exception as e:
        logger.error(f"MacroIndicators node error: {e}")
        return {"errors": [str(e)]}


async def fundamental_analysis_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for FundamentalAnalysis agent.
    Uses FundamentalScanner for deterministic analysis.
    """
    resources = NodeResources()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    raw_data = params.get("raw_data", {})
    
    try:
        from quant.fundamentals import FundamentalScanner
        scanner = FundamentalScanner()
        scan_results = scanner.scan(raw_data)
        
        return {
            "agent_outputs": {"fundamental_analysis": json.dumps(scan_results)},
            "tool_registry": [{
                "tool_name": "analysis:run_fundamental_scan",
                "input_parameters": params,
                "output_data": scan_results,
                "extracted_metrics": {}
            }]
        }
    except Exception as e:
        logger.error(f"FundamentalAnalysis node error: {e}")
        return {"errors": [str(e)]}


async def technical_analysis_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for TechnicalAnalysis agent.
    Uses TechnicalScanner for indicator calculations.
    """
    resources = NodeResources()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    ohlcv_data = params.get("ohlcv_data", [])
    
    try:
        import pandas as pd
        from quant.indicators import TechnicalScanner
        
        df = pd.DataFrame(ohlcv_data)
        scanner = TechnicalScanner()
        scan_results = scanner.scan(df)
        
        return {
            "agent_outputs": {"technical_analysis": json.dumps(scan_results)},
            "tool_registry": [{
                "tool_name": "analysis:run_technical_scan",
                "input_parameters": params,
                "output_data": scan_results,
                "extracted_metrics": {}
            }]
        }
    except Exception as e:
        logger.error(f"TechnicalAnalysis node error: {e}")
        return {"errors": [str(e)]}


async def sentiment_analysis_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for SentimentAnalysis agent.
    Uses LLM for sentiment analysis.
    """
    resources = NodeResources()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    text = params.get("text", "")
    
    try:
        prompt = f"Analyze the sentiment of this text: {text}"
        response = await resources.llm.generate_message(
            messages=[Message(role="user", content=prompt)],
            model="mistral-8b"
        )
        
        result = {"text": text, "analysis": response.content}
        
        return {
            "agent_outputs": {"sentiment_analysis": json.dumps(result)},
            "tool_registry": [{
                "tool_name": "analysis:analyze_sentiment",
                "input_parameters": params,
                "output_data": result,
                "extracted_metrics": {}
            }]
        }
    except Exception as e:
        logger.error(f"SentimentAnalysis node error: {e}")
        return {"errors": [str(e)]}


async def macro_analysis_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for MacroAnalysis agent.
    Analyzes macroeconomic trends.
    """
    resources = NodeResources()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    macro_data = params.get("macro_data", {})
    
    try:
        prompt = f"Analyze these macroeconomic indicators: {json.dumps(macro_data)}"
        response = await resources.llm.generate_message(
            messages=[Message(role="user", content=prompt)],
            model="mistral-8b"
        )
        
        result = {"macro_data": macro_data, "analysis": response.content}
        
        return {
            "agent_outputs": {"macro_analysis": json.dumps(result)},
            "tool_registry": [{
                "tool_name": "analysis:analyze_macro",
                "input_parameters": params,
                "output_data": result,
                "extracted_metrics": {}
            }]
        }
    except Exception as e:
        logger.error(f"MacroAnalysis node error: {e}")
        return {"errors": [str(e)]}


async def contrarian_analysis_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for ContrarianAnalysis agent.
    Generates contrarian investment signals.
    """
    resources = NodeResources()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    market_data = params.get("market_data", {})
    sentiment_data = params.get("sentiment_data", {})
    
    try:
        prompt = f"Provide a contrarian analysis based on: Market Data: {json.dumps(market_data)}, Sentiment: {json.dumps(sentiment_data)}"
        response = await resources.llm.generate_message(
            messages=[Message(role="user", content=prompt)],
            model="mistral-8b"
        )
        
        result = {"market_data": market_data, "sentiment": sentiment_data, "analysis": response.content}
        
        return {
            "agent_outputs": {"contrarian_analysis": json.dumps(result)},
            "tool_registry": [{
                "tool_name": "analysis:analyze_contrarian",
                "input_parameters": params,
                "output_data": result,
                "extracted_metrics": {}
            }]
        }
    except Exception as e:
        logger.error(f"ContrarianAnalysis node error: {e}")
        return {"errors": [str(e)]}


async def retrieval_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    Stateless node for Retrieval agent.
    Searches vector database for context.
    """
    resources = NodeResources()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    query = params.get("query", "")
    
    try:
        results = resources.vector_db.hybrid_search(query, limit=5)
        
        return {
            "agent_outputs": {"retrieval": json.dumps({"results": results})},
            "tool_registry": [{
                "tool_name": "retrieval:hybrid_search",
                "input_parameters": params,
                "output_data": {"results": results},
                "extracted_metrics": {}
            }]
        }
    except Exception as e:
        logger.error(f"Retrieval node error: {e}")
        return {"errors": [str(e)]}
