"""Central registry of agent nodes for orchestration."""
from typing import Dict, Any, Callable
from app.core.graph.nodes.data_nodes import (
    market_offline_node,
    price_and_fundamentals_node,
    market_news_node,
    macro_indicators_node,
    retrieval_node,
    web_search_node,
)
from app.core.graph.nodes.analysis_nodes import (
    fundamental_analysis_node,
    technical_analysis_node,
    sentiment_analysis_node,
    macro_analysis_node,
    contrarian_analysis_node,
)

AGENT_NODE_MAP: Dict[str, Callable] = {
    "market_offline": market_offline_node,
    "market_online": price_and_fundamentals_node,
    "price_and_fundamentals": price_and_fundamentals_node,
    "market_news": market_news_node,
    "macro_indicators": macro_indicators_node,
    "retrieval": retrieval_node,
    "web_search": web_search_node,
    "fundamental_analysis": fundamental_analysis_node,
    "sentiment_analysis": sentiment_analysis_node,
    "macro_analysis": macro_analysis_node,
    "technical_analysis": technical_analysis_node,
    "contrarian_analysis": contrarian_analysis_node,
}
