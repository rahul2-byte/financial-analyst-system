from typing import Any

from agents.financial.analysis.fundamental import fundamental_analysis_node
from agents.financial.analysis.technical import technical_analysis_node
from agents.financial.analysis.sentiment import sentiment_analysis_node
from agents.financial.analysis.macro import macro_analysis_node
from agents.financial.analysis.contrarian import contrarian_analysis_node

AGENT_NODE_MAP: dict[str, Any] = {
    "fundamental_analysis": fundamental_analysis_node,
    "technical_analysis": technical_analysis_node,
    "sentiment_analysis": sentiment_analysis_node,
    "macro_analysis": macro_analysis_node,
    "contrarian_analysis": contrarian_analysis_node,
}
