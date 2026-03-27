from typing import Any, Dict, Optional, Callable, List
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Optional[Callable] = None


class ToolRegistry:
    """Singleton registry for all tools in the system."""
    _instance: Optional["ToolRegistry"] = None
    _tools: Dict[str, ToolDefinition] = {}

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._tools = {}
        return cls._instance

    def register(self, namespace: str, tool: ToolDefinition) -> None:
        full_name = f"{namespace}:{tool.name}"
        self._tools[full_name] = tool

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def get_tools_by_namespace(self, namespace: str) -> List[ToolDefinition]:
        prefix = f"{namespace}:"
        return [t for name, t in self._tools.items() if name.startswith(prefix)]

    def clear(self) -> None:
        self._tools.clear()

    def register_predefined_tools(self) -> None:
        """Register all tools from all agents."""
        
        # ==================== MARKET OFFLINE TOOLS ====================
        self.register("market", ToolDefinition(
            name="check_db_status",
            description="Checks if the PostgreSQL database is up and running.",
            parameters={"type": "object", "properties": {}, "required": []},
        ))
        self.register("market", ToolDefinition(
            name="get_table_names",
            description="Gets a list of all table names in the database.",
            parameters={"type": "object", "properties": {}, "required": []},
        ))
        self.register("market", ToolDefinition(
            name="get_column_names",
            description="Gets a list of column names for a specific table.",
            parameters={
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "The name of the table to inspect."}
                },
                "required": ["table_name"],
            },
        ))
        self.register("market", ToolDefinition(
            name="get_ticker_info",
            description="Gets specific info for a stock ticker: date ranges, row counts, and if it was found.",
            parameters={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "The stock ticker symbol (e.g., 'RELIANCE.NS')."}
                },
                "required": ["ticker"],
            },
        ))
        self.register("market", ToolDefinition(
            name="submit_offline_status",
            description="Submits the final determination of whether the data is available offline.",
            parameters={
                "type": "object",
                "properties": {
                    "data_available": {"type": "boolean"},
                    "summary": {"type": "string", "description": "Brief explanation of why the data is or is not available."},
                },
                "required": ["data_available", "summary"],
            },
        ))

        # ==================== PRICE & FUNDAMENTALS TOOLS ====================
        self.register("data", ToolDefinition(
            name="fetch_stock_data",
            description="Fetches stock price data (OHLCV) for a given ticker and timeframe.",
            parameters={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol"},
                    "period": {"type": "string", "description": "Time period (e.g., '1y', '6mo')"},
                },
                "required": ["ticker"],
            },
        ))
        self.register("data", ToolDefinition(
            name="fetch_fundamentals",
            description="Fetches company fundamental data (P/E, EPS, etc.)",
            parameters={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol"},
                },
                "required": ["ticker"],
            },
        ))
        self.register("data", ToolDefinition(
            name="submit_data_response",
            description="Submits the fetched market data.",
            parameters={
                "type": "object",
                "properties": {
                    "data": {"type": "object", "description": "The market data to submit"},
                },
                "required": ["data"],
            },
        ))

        # ==================== MARKET NEWS TOOLS ====================
        self.register("news", ToolDefinition(
            name="fetch_news",
            description="Fetches latest market news from RSS feeds.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Topic to search for"},
                    "limit": {"type": "integer", "description": "Number of articles to fetch"},
                },
                "required": ["query"],
            },
        ))
        self.register("news", ToolDefinition(
            name="search_vector_db",
            description="Searches vector database for relevant context.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results"},
                },
                "required": ["query"],
            },
        ))
        self.register("news", ToolDefinition(
            name="submit_news_summary",
            description="Submits the final news summary.",
            parameters={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["summary"],
            },
        ))

        # ==================== MACRO INDICATORS TOOLS ====================
        self.register("macro", ToolDefinition(
            name="fetch_macro_data",
            description="Fetches macroeconomic indicator data.",
            parameters={
                "type": "object",
                "properties": {
                    "indicator": {"type": "string", "description": "Indicator name (e.g., GDP, Inflation)"},
                    "country": {"type": "string", "description": "Country code"},
                },
                "required": ["indicator"],
            },
        ))
        self.register("macro", ToolDefinition(
            name="calculate_indicators",
            description="Calculates derived macro indicators.",
            parameters={
                "type": "object",
                "properties": {
                    "raw_data": {"type": "object"},
                },
                "required": ["raw_data"],
            },
        ))

        # ==================== FUNDAMENTAL ANALYSIS TOOLS ====================
        self.register("analysis", ToolDefinition(
            name="run_fundamental_scan",
            description="Runs deterministic quantitative analysis on raw financial data to evaluate valuation, health, and profitability.",
            parameters={
                "type": "object",
                "properties": {
                    "raw_data": {"type": "string", "description": "The raw JSON string of fundamental data."},
                },
                "required": ["raw_data"],
            },
        ))
        self.register("analysis", ToolDefinition(
            name="submit_thesis",
            description="Submits the final investment thesis and key findings.",
            parameters={
                "type": "object",
                "properties": {
                    "investment_thesis": {"type": "string"},
                    "key_findings": {"type": "array", "items": {"type": "string"}},
                    "confidence_score": {"type": "number"},
                },
                "required": ["investment_thesis", "key_findings", "confidence_score"],
            },
        ))

        # ==================== TECHNICAL ANALYSIS TOOLS ====================
        self.register("analysis", ToolDefinition(
            name="run_technical_scan",
            description="Calculates technical indicators like RSI, MACD, and Bollinger Bands from OHLCV price data.",
            parameters={
                "type": "object",
                "properties": {
                    "ohlcv_data": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "timestamp": {"type": "string"},
                                "open": {"type": "number"},
                                "high": {"type": "number"},
                                "low": {"type": "number"},
                                "close": {"type": "number"},
                                "volume": {"type": "number"},
                            },
                            "required": ["close"],
                        },
                    },
                },
                "required": ["ohlcv_data"],
            },
        ))
        self.register("analysis", ToolDefinition(
            name="submit_technical_report",
            description="Submits the final technical analysis trend report.",
            parameters={
                "type": "object",
                "properties": {
                    "trend": {"type": "string", "enum": ["Bullish", "Bearish", "Neutral"]},
                    "report_summary": {"type": "string"},
                    "key_indicators": {"type": "object"},
                    "reversal_points": {"type": "array", "items": {"type": "number"}},
                },
                "required": ["trend", "report_summary", "key_indicators"],
            },
        ))

        # ==================== SENTIMENT ANALYSIS TOOLS ====================
        self.register("analysis", ToolDefinition(
            name="analyze_sentiment",
            description="Analyzes sentiment from text data.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to analyze"},
                },
                "required": ["text"],
            },
        ))
        self.register("analysis", ToolDefinition(
            name="submit_sentiment",
            description="Submits the sentiment analysis results.",
            parameters={
                "type": "object",
                "properties": {
                    "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                    "score": {"type": "number"},
                    "summary": {"type": "string"},
                },
                "required": ["sentiment", "score"],
            },
        ))

        # ==================== MACRO ANALYSIS TOOLS ====================
        self.register("analysis", ToolDefinition(
            name="analyze_macro",
            description="Analyzes macroeconomic trends and their impact.",
            parameters={
                "type": "object",
                "properties": {
                    "macro_data": {"type": "object"},
                },
                "required": ["macro_data"],
            },
        ))
        self.register("analysis", ToolDefinition(
            name="submit_macro_report",
            description="Submits the macroeconomic analysis report.",
            parameters={
                "type": "object",
                "properties": {
                    "outlook": {"type": "string"},
                    "key_factors": {"type": "array", "items": {"type": "string"}},
                    "impact": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                },
                "required": ["outlook", "impact"],
            },
        ))

        # ==================== CONTRARIAN ANALYSIS TOOLS ====================
        self.register("analysis", ToolDefinition(
            name="analyze_contrarian",
            description="Analyzes data for contrarian investment signals.",
            parameters={
                "type": "object",
                "properties": {
                    "market_data": {"type": "object"},
                    "sentiment_data": {"type": "object"},
                },
                "required": ["market_data"],
            },
        ))
        self.register("analysis", ToolDefinition(
            name="submit_contrarian_report",
            description="Submits the contrarian analysis report.",
            parameters={
                "type": "object",
                "properties": {
                    "signal": {"type": "string", "enum": ["buy", "sell", "neutral"]},
                    "rationale": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["signal", "rationale"],
            },
        ))

        # ==================== RETRIEVAL TOOLS ====================
        self.register("retrieval", ToolDefinition(
            name="hybrid_search",
            description="Performs hybrid search (vector + keyword) on the knowledge base.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        ))
        self.register("retrieval", ToolDefinition(
            name="submit_retrieval_results",
            description="Submits the retrieval results.",
            parameters={
                "type": "object",
                "properties": {
                    "results": {"type": "array"},
                },
                "required": ["results"],
            },
        ))

        # ==================== WEB SEARCH TOOLS ====================
        self.register("research", ToolDefinition(
            name="search_web",
            description="Searches the web for information.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "num_results": {"type": "integer"},
                },
                "required": ["query"],
            },
        ))
        self.register("research", ToolDefinition(
            name="submit_search_results",
            description="Submits the web search results.",
            parameters={
                "type": "object",
                "properties": {
                    "results": {"type": "array"},
                },
                "required": ["results"],
            },
        ))

        # ==================== VALIDATION TOOLS ====================
        self.register("validation", ToolDefinition(
            name="validate_report",
            description="Validates the draft report for compliance and safety.",
            parameters={
                "type": "object",
                "properties": {
                    "report": {"type": "string"},
                    "user_query": {"type": "string"},
                },
                "required": ["report"],
            },
        ))

        logger.info(f"Registered {len(self._tools)} tools")


def get_registry() -> ToolRegistry:
    """Get the singleton ToolRegistry instance."""
    return ToolRegistry()


def _register_predefined_tools() -> None:
    registry = ToolRegistry()
    registry.clear()
    registry.register_predefined_tools()


# Initialize on import
_register_predefined_tools()
