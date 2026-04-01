"""Analysis-oriented graph node handlers."""

import json
from typing import Any, Dict

import pandas as pd

from app.config import settings
from app.core.graph.graph_state import ResearchGraphState
from app.core.graph.node_helpers import build_node_error, build_node_success
from app.core.node_resources import NodeResources
from app.models.request_models import Message
from quant.fundamentals import FundamentalScanner
from quant.indicators import TechnicalScanner


async def fundamental_analysis_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Uses FundamentalScanner for deterministic analysis."""
    params = state.get("current_step", {}).get("parameters", {})
    raw_data = params.get("raw_data", {})
    try:
        scanner = FundamentalScanner()
        scan_results = scanner.scan(raw_data)
        return build_node_success(
            agent_output_key="fundamental_analysis",
            agent_output=scan_results,
            tool_name="analysis:run_fundamental_scan",
            input_parameters=params,
            tool_output=scan_results,
        )
    except Exception as error:
        return build_node_error(error)


async def technical_analysis_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Uses TechnicalScanner for indicator calculations."""
    params = state.get("current_step", {}).get("parameters", {})
    ohlcv_data = params.get("ohlcv_data", [])
    try:
        dataframe = pd.DataFrame(ohlcv_data)
        scanner = TechnicalScanner()
        scan_results = scanner.scan(dataframe)
        return build_node_success(
            agent_output_key="technical_analysis",
            agent_output=scan_results,
            tool_name="analysis:run_technical_scan",
            input_parameters=params,
            tool_output=scan_results,
        )
    except Exception as error:
        return build_node_error(error)


async def sentiment_analysis_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Uses LLM for sentiment analysis."""
    params = state.get("current_step", {}).get("parameters", {})
    text = params.get("text", "")
    try:
        prompt = f"Analyze the sentiment of this text: {text}"
        response = await resources.llm_service.generate_message(
            messages=[Message(role="user", content=prompt)],
            model=settings.DEFAULT_LLM_MODEL,
        )
        result = {"text": text, "analysis": response.content}
        return build_node_success(
            agent_output_key="sentiment_analysis",
            agent_output=result,
            tool_name="analysis:analyze_sentiment",
            input_parameters=params,
            tool_output=result,
        )
    except Exception as error:
        return build_node_error(error)


async def macro_analysis_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Analyzes macroeconomic trends."""
    params = state.get("current_step", {}).get("parameters", {})
    macro_data = params.get("macro_data", {})
    try:
        prompt = f"Analyze these macroeconomic indicators: {json.dumps(macro_data)}"
        response = await resources.llm_service.generate_message(
            messages=[Message(role="user", content=prompt)],
            model=settings.DEFAULT_LLM_MODEL,
        )
        result = {"macro_data": macro_data, "analysis": response.content}
        return build_node_success(
            agent_output_key="macro_analysis",
            agent_output=result,
            tool_name="analysis:analyze_macro",
            input_parameters=params,
            tool_output=result,
        )
    except Exception as error:
        return build_node_error(error)


async def contrarian_analysis_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Generates contrarian investment signals."""
    params = state.get("current_step", {}).get("parameters", {})
    market_data = params.get("market_data", {})
    sentiment_data = params.get("sentiment_data", {})
    try:
        prompt = (
            "Provide a contrarian analysis based on: "
            f"Market Data: {json.dumps(market_data)}, "
            f"Sentiment: {json.dumps(sentiment_data)}"
        )
        response = await resources.llm_service.generate_message(
            messages=[Message(role="user", content=prompt)],
            model=settings.DEFAULT_LLM_MODEL,
        )
        result = {
            "market_data": market_data,
            "sentiment": sentiment_data,
            "analysis": response.content,
        }
        return build_node_success(
            agent_output_key="contrarian_analysis",
            agent_output=result,
            tool_name="analysis:analyze_contrarian",
            input_parameters=params,
            tool_output=result,
        )
    except Exception as error:
        return build_node_error(error)
