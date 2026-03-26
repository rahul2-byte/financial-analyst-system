import asyncio
import logging
from typing import List, Set, Dict, Any, Optional

from app.core.graph_state import ResearchGraphState
from app.services.llm_interface import LLMServiceInterface
from app.services.llama_cpp_service import LlamaCppService
from storage.sql.client import PostgresClient
from storage.vector.client import QdrantStorage
from data.providers.yfinance import YFinanceFetcher
from data.providers.rss_news import RSSNewsFetcher

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

logger = logging.getLogger(__name__)


AGENT_MAP: Dict[str, BaseAgent] = {}


def _initialize_agents():
    """Initialize agents once for reuse across node calls."""
    global AGENT_MAP
    if AGENT_MAP:
        return

    llm = LlamaCppService()
    sql_db = PostgresClient()
    vector_db = QdrantStorage()
    yf_fetcher = YFinanceFetcher()
    rss_fetcher = RSSNewsFetcher()

    AGENT_MAP["planner"] = PlannerAgent(llm_service=llm)
    AGENT_MAP["market_offline"] = MarketOfflineAgent(llm_service=llm, db_client=sql_db)
    AGENT_MAP["price_and_fundamentals"] = PriceAndFundamentalsAgent(
        llm_service=llm, yf_fetcher=yf_fetcher, sql_db=sql_db
    )
    AGENT_MAP["market_news"] = MarketNewsAgent(
        llm_service=llm, rss_fetcher=rss_fetcher, vector_db=vector_db
    )
    AGENT_MAP["macro_indicators"] = MacroIndicatorsAgent(
        llm_service=llm, yf_fetcher=yf_fetcher, sql_db=sql_db
    )
    AGENT_MAP["retrieval"] = RetrievalAgent(llm_service=llm, qdrant_client=vector_db)
    AGENT_MAP["fundamental_analysis"] = FundamentalAnalysisAgent(llm_service=llm)
    AGENT_MAP["sentiment_analysis"] = SentimentAnalysisAgent(llm_service=llm)
    AGENT_MAP["macro_analysis"] = MacroAnalysisAgent(llm_service=llm)
    AGENT_MAP["technical_analysis"] = TechnicalAnalysisAgent(llm_service=llm)
    AGENT_MAP["contrarian_analysis"] = ContrarianAgent(llm_service=llm)


def _get_agent_name(step: ExecutionStep) -> str:
    """Extract agent name from step target."""
    if hasattr(step.target_agent, "value"):
        return step.target_agent.value
    return str(step.target_agent)


async def planner_node(state: ResearchGraphState) -> Dict[str, Any]:
    """Wraps PlannerAgent to generate execution plan from user query."""
    _initialize_agents()

    user_query = state["user_query"]
    conversation_history = state.get("conversation_history", [])

    planner = AGENT_MAP["planner"]
    context = {"conversation_history": conversation_history}

    logger.info(f"Planner node processing query: {user_query}")
    response = await planner.execute(user_query, context=context)

    if response.status == "failure" or not response.data:
        logger.error(f"Planner failed: {response.errors}")
        return {
            "plan": None,
            "errors": [f"Planning failed: {response.errors}"]
        }

    plan_data = (
        response.data
        if isinstance(response.data, PlanData)
        else PlanData(**response.data)
    )

    logger.info(f"Planner generated {len(plan_data.execution_steps)} steps")

    return {
        "plan": plan_data.model_dump() if hasattr(plan_data, "model_dump") else plan_data,
    }


def _group_steps(steps: List[ExecutionStep]) -> List[List[ExecutionStep]]:
    """Groups steps into levels based on dependencies for parallel execution."""
    levels = []
    executed_step_ids: Set[int] = set()
    remaining_steps = list(steps)

    while remaining_steps:
        current_level = []
        for step in remaining_steps[:]:
            if all(dep in executed_step_ids for dep in step.dependencies):
                current_level.append(step)
                remaining_steps.remove(step)

        if not current_level:
            logger.error("Circular dependency detected in execution plan.")
            break

        levels.append(current_level)
        for step in current_level:
            executed_step_ids.add(step.step_number)

    return levels


def _find_next_level(
    steps: List[ExecutionStep],
    executed_step_ids: Set[int]
) -> List[ExecutionStep]:
    """Find steps where all dependencies have been executed."""
    return [
        step for step in steps
        if all(dep in executed_step_ids for dep in step.dependencies)
    ]


async def execute_level_node(state: ResearchGraphState) -> Dict[str, Any]:
    """Executes the next level of steps in parallel where dependencies are met."""
    _initialize_agents()

    plan_data = state.get("plan")
    if not plan_data:
        return {"errors": ["No plan in state"]}

    if isinstance(plan_data, dict):
        execution_steps = plan_data.get("execution_steps", [])
        execution_steps = [ExecutionStep(**s) for s in execution_steps]
    else:
        execution_steps = plan_data.execution_steps

    current_executed = state.get("executed_steps", [])
    executed_step_ids = {s.get("step_number", s.step_number if hasattr(s, "step_number") else -1) for s in current_executed}

    next_level = _find_next_level(execution_steps, executed_step_ids)

    if not next_level:
        if len(current_executed) < len(execution_steps):
            return {"errors": ["No steps ready to execute - possible circular dependency"]}
        return {"agent_outputs": state.get("agent_outputs", {}), "executed_steps": current_executed}

    agent_tasks = []
    for step in next_level:
        agent_name = _get_agent_name(step)
        agent = AGENT_MAP.get(agent_name)
        if not agent:
            logger.warning(f"Agent {agent_name} not found in agent map")
            continue

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
    new_tool_registry = list(state.get("tool_registry", []))
    new_executed_steps = list(current_executed)

    for step, result in zip(next_level, results):
        agent_name = _get_agent_name(step)
        if isinstance(result, Exception):
            logger.error(f"Step {step.step_number} failed: {result}")
            new_agent_outputs[str(step.step_number)] = f"Error: {str(result)}"
        else:
            new_agent_outputs[str(step.step_number)] = result.get("output", "")

        new_executed_steps.append({"step_number": step.step_number, "agent": agent_name})

    return {
        "agent_outputs": new_agent_outputs,
        "tool_registry": new_tool_registry,
        "executed_steps": new_executed_steps,
    }


async def _execute_single_step(
    agent: BaseAgent,
    query: str,
    step: ExecutionStep
) -> Dict[str, Any]:
    """Executes a single agent step and returns output."""
    try:
        result = await agent.execute(query, step_number=step.step_number)
        if result.status == "success":
            output = ""
            if isinstance(result.data, dict) and "response" in result.data:
                output = result.data["response"]
            elif isinstance(result.data, dict):
                import json
                output = json.dumps(result.data)
            else:
                output = str(result.data)
            return {"output": output, "data": result.data}
        else:
            return {"output": f"Error: {result.errors}", "data": None}
    except Exception as e:
        return {"output": f"Exception: {str(e)}", "data": None}