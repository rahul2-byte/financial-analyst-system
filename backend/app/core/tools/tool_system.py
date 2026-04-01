"""
Legacy Tool System (non-canonical runtime path).

This module consolidates:
- Tool definitions and registry
- Tool handlers/executors
- Centralized tool execution

Note:
    Canonical runtime execution is graph-node based (see app.core.graph*).
    This module remains temporarily for compatibility and tests only.

Usage:
    from app.core.tools.tool_system import tool_registry, tool_executor, get_tool_handler

    tool = tool_registry.get_tool("market:check_db_status")
    result = tool_executor.execute("market:check_db_status", {})
"""

import json
import logging
from typing import Any, Dict, Optional, Callable, Awaitable, Union
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ToolNamespace(str, Enum):
    """Enumeration of tool namespaces."""

    MARKET = "market"
    DATA = "data"
    NEWS = "news"
    MACRO = "macro"
    ANALYSIS = "analysis"
    RETRIEVAL = "retrieval"
    RESEARCH = "research"
    VALIDATION = "validation"


@dataclass
class ToolDefinition:
    """Definition of a tool with metadata and handler."""

    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Optional[Callable[..., Any]] = None
    namespace: ToolNamespace = ToolNamespace.DATA

    @property
    def full_name(self) -> str:
        return f"{self.namespace.value}:{self.name}"


@dataclass
class ToolResult:
    """Result of tool execution."""

    success: bool
    data: Any = None
    error: Optional[str] = None
    delegate_to_agent: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"success": self.success}
        if self.data is not None:
            result["data"] = self.data
        if self.error:
            result["error"] = self.error
        if self.delegate_to_agent:
            result["delegate_to_agent"] = self.delegate_to_agent
        return result


class ToolRegistry:
    """
    Registry for all tools in the system.

    Supports:
    - Registration of tools with namespaces
    - Lookup by full name or namespace:name
    - Listing tools by namespace
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._initialized = False

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool in the registry."""
        self._tools[tool.full_name] = tool
        logger.debug(f"Registered tool: {tool.full_name}")

    def get_tool(self, full_name: str) -> Optional[ToolDefinition]:
        """Get a tool by its full name (namespace:name)."""
        return self._tools.get(full_name)

    def list_tools(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_tools_by_namespace(
        self, namespace: Union[str, ToolNamespace]
    ) -> list[ToolDefinition]:
        """Get all tools in a namespace."""
        ns = namespace.value if isinstance(namespace, ToolNamespace) else namespace
        return [t for t in self._tools.values() if t.namespace.value == ns]

    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> None:
        """Initialize with predefined tools."""
        if self._initialized:
            return
        self._register_predefined_tools()
        self._initialized = True

    def _register_predefined_tools(self) -> None:
        """Register all predefined tools."""
        tools = [
            ToolDefinition(
                name="check_db_status",
                description="Checks if the PostgreSQL database is up and running.",
                parameters={"type": "object", "properties": {}, "required": []},
                namespace=ToolNamespace.MARKET,
            ),
            ToolDefinition(
                name="get_table_names",
                description="Gets a list of all table names in the database.",
                parameters={"type": "object", "properties": {}, "required": []},
                namespace=ToolNamespace.MARKET,
            ),
            ToolDefinition(
                name="get_column_names",
                description="Gets a list of column names for a specific table.",
                parameters={
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "The name of the table to inspect.",
                        }
                    },
                    "required": ["table_name"],
                },
                namespace=ToolNamespace.MARKET,
            ),
            ToolDefinition(
                name="get_ticker_info",
                description="Gets specific info for a stock ticker: date ranges, row counts, and if it was found.",
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "The stock ticker symbol (e.g., 'RELIANCE.NS').",
                        }
                    },
                    "required": ["ticker"],
                },
                namespace=ToolNamespace.MARKET,
            ),
            ToolDefinition(
                name="search_tickers",
                description="Fuzzy search for tickers in the database if the exact one is not found.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (ticker or company name)",
                        }
                    },
                    "required": ["query"],
                },
                namespace=ToolNamespace.MARKET,
            ),
            ToolDefinition(
                name="submit_offline_status",
                description="Submits the final determination of whether the data is available offline.",
                parameters={
                    "type": "object",
                    "properties": {
                        "data_available": {"type": "boolean"},
                        "ticker_used": {"type": "string"},
                        "reasoning": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["data_available", "ticker_used", "reasoning"],
                },
                namespace=ToolNamespace.MARKET,
            ),
            ToolDefinition(
                name="fetch_stock_data",
                description="Fetches stock price data (OHLCV) for a given ticker and timeframe.",
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Stock ticker symbol",
                        },
                        "period": {
                            "type": "string",
                            "description": "Time period (e.g., '1y', '6mo')",
                        },
                    },
                    "required": ["ticker"],
                },
                namespace=ToolNamespace.DATA,
            ),
            ToolDefinition(
                name="fetch_fundamentals",
                description="Fetches company fundamental data (P/E, EPS, etc.)",
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Stock ticker symbol",
                        }
                    },
                    "required": ["ticker"],
                },
                namespace=ToolNamespace.DATA,
            ),
            ToolDefinition(
                name="submit_data_response",
                description="Submits the fetched market data.",
                parameters={
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "object",
                            "description": "The market data to submit",
                        }
                    },
                    "required": ["data"],
                },
                namespace=ToolNamespace.DATA,
            ),
            ToolDefinition(
                name="fetch_news",
                description="Fetches latest market news from RSS feeds.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Topic to search for",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of articles to fetch",
                        },
                    },
                    "required": ["query"],
                },
                namespace=ToolNamespace.NEWS,
            ),
            ToolDefinition(
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
                namespace=ToolNamespace.NEWS,
            ),
            ToolDefinition(
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
                namespace=ToolNamespace.NEWS,
            ),
            ToolDefinition(
                name="fetch_macro_data",
                description="Fetches macroeconomic indicator data.",
                parameters={
                    "type": "object",
                    "properties": {
                        "indicator": {
                            "type": "string",
                            "description": "Indicator name (e.g., GDP, Inflation)",
                        },
                        "country": {"type": "string", "description": "Country code"},
                    },
                    "required": ["indicator"],
                },
                namespace=ToolNamespace.MACRO,
            ),
            ToolDefinition(
                name="calculate_indicators",
                description="Calculates derived macro indicators.",
                parameters={
                    "type": "object",
                    "properties": {"raw_data": {"type": "object"}},
                    "required": ["raw_data"],
                },
                namespace=ToolNamespace.MACRO,
            ),
            ToolDefinition(
                name="run_fundamental_scan",
                description="Runs deterministic quantitative analysis on raw financial data to evaluate valuation, health, and profitability.",
                parameters={
                    "type": "object",
                    "properties": {
                        "raw_data": {
                            "type": "string",
                            "description": "The raw JSON string of fundamental data.",
                        }
                    },
                    "required": ["raw_data"],
                },
                namespace=ToolNamespace.ANALYSIS,
            ),
            ToolDefinition(
                name="submit_thesis",
                description="Submits the final investment thesis and key findings.",
                parameters={
                    "type": "object",
                    "properties": {
                        "investment_thesis": {"type": "string"},
                        "key_findings": {"type": "array", "items": {"type": "string"}},
                        "confidence_score": {"type": "number"},
                    },
                    "required": [
                        "investment_thesis",
                        "key_findings",
                        "confidence_score",
                    ],
                },
                namespace=ToolNamespace.ANALYSIS,
            ),
            ToolDefinition(
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
                namespace=ToolNamespace.ANALYSIS,
            ),
            ToolDefinition(
                name="submit_technical_report",
                description="Submits the final technical analysis trend report.",
                parameters={
                    "type": "object",
                    "properties": {
                        "trend": {
                            "type": "string",
                            "enum": ["Bullish", "Bearish", "Neutral"],
                        },
                        "report_summary": {"type": "string"},
                        "key_indicators": {"type": "object"},
                        "reversal_points": {
                            "type": "array",
                            "items": {"type": "number"},
                        },
                    },
                    "required": ["trend", "report_summary", "key_indicators"],
                },
                namespace=ToolNamespace.ANALYSIS,
            ),
            ToolDefinition(
                name="analyze_sentiment",
                description="Analyzes sentiment from text data.",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to analyze"}
                    },
                    "required": ["text"],
                },
                namespace=ToolNamespace.ANALYSIS,
            ),
            ToolDefinition(
                name="submit_sentiment",
                description="Submits the sentiment analysis results.",
                parameters={
                    "type": "object",
                    "properties": {
                        "sentiment": {
                            "type": "string",
                            "enum": ["positive", "negative", "neutral"],
                        },
                        "score": {"type": "number"},
                        "summary": {"type": "string"},
                    },
                    "required": ["sentiment", "score"],
                },
                namespace=ToolNamespace.ANALYSIS,
            ),
            ToolDefinition(
                name="analyze_macro",
                description="Analyzes macroeconomic trends and their impact.",
                parameters={
                    "type": "object",
                    "properties": {"macro_data": {"type": "object"}},
                    "required": ["macro_data"],
                },
                namespace=ToolNamespace.ANALYSIS,
            ),
            ToolDefinition(
                name="submit_macro_report",
                description="Submits the macroeconomic analysis report.",
                parameters={
                    "type": "object",
                    "properties": {
                        "outlook": {"type": "string"},
                        "key_factors": {"type": "array", "items": {"type": "string"}},
                        "impact": {
                            "type": "string",
                            "enum": ["positive", "negative", "neutral"],
                        },
                    },
                    "required": ["outlook", "impact"],
                },
                namespace=ToolNamespace.ANALYSIS,
            ),
            ToolDefinition(
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
                namespace=ToolNamespace.ANALYSIS,
            ),
            ToolDefinition(
                name="submit_contrarian_report",
                description="Submits the contrarian analysis report.",
                parameters={
                    "type": "object",
                    "properties": {
                        "signal": {
                            "type": "string",
                            "enum": ["buy", "sell", "neutral"],
                        },
                        "rationale": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["signal", "rationale"],
                },
                namespace=ToolNamespace.ANALYSIS,
            ),
            ToolDefinition(
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
                namespace=ToolNamespace.RETRIEVAL,
            ),
            ToolDefinition(
                name="submit_retrieval_results",
                description="Submits the retrieval results.",
                parameters={
                    "type": "object",
                    "properties": {"results": {"type": "array"}},
                    "required": ["results"],
                },
                namespace=ToolNamespace.RETRIEVAL,
            ),
            ToolDefinition(
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
                namespace=ToolNamespace.RESEARCH,
            ),
            ToolDefinition(
                name="submit_search_results",
                description="Submits the web search results.",
                parameters={
                    "type": "object",
                    "properties": {"results": {"type": "array"}},
                    "required": ["results"],
                },
                namespace=ToolNamespace.RESEARCH,
            ),
            ToolDefinition(
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
                namespace=ToolNamespace.VALIDATION,
            ),
        ]

        for tool in tools:
            self.register(tool)

        logger.info(f"Registered {len(self._tools)} predefined tools")


class ToolExecutor:
    """
    Centralized tool executor that handles tool execution and delegation.
    """

    def __init__(self, registry: Optional[ToolRegistry] = None):
        self.registry = registry or tool_registry
        self._handlers: Dict[str, Callable[..., Any]] = {}
        self._initialized = False

    def register_handler(
        self, tool_full_name: str, handler: Callable[..., Any]
    ) -> None:
        """Register a handler for a specific tool."""
        self._handlers[tool_full_name] = handler

    def initialize(self) -> None:
        """Initialize with predefined handlers."""
        if self._initialized:
            return
        self._register_predefined_handlers()
        self._initialized = True

    def _register_predefined_handlers(self) -> None:
        """Register all predefined tool handlers."""
        from storage.sql.client import PostgresClient
        from quant.fundamentals import FundamentalScanner
        import pandas as pd

        handlers: Dict[str, Callable[..., Any]] = {
            "market:check_db_status": lambda args: {
                "db_up": PostgresClient().is_db_up()
            },
            "market:get_table_names": lambda args: {
                "tables": PostgresClient().get_table_names()
            },
            "market:get_column_names": lambda args: {
                "columns": PostgresClient().get_column_names(args.get("table_name", ""))
            },
            "market:get_ticker_info": lambda args: PostgresClient().get_ticker_info(
                args.get("ticker", "")
            ),
            "market:search_tickers": lambda args: {
                "matches": PostgresClient().search_tickers(args.get("query", ""))
            },
            "market:submit_offline_status": lambda args: args,
            "data:fetch_stock_data": lambda args: {
                "delegate_to_agent": "price_and_fundamentals"
            },
            "data:fetch_fundamentals": lambda args: {
                "delegate_to_agent": "price_and_fundamentals"
            },
            "data:submit_data_response": lambda args: args,
            "news:fetch_news": lambda args: {"delegate_to_agent": "market_news"},
            "news:search_vector_db": lambda args: {"delegate_to_agent": "retrieval"},
            "news:submit_news_summary": lambda args: args,
            "macro:fetch_macro_data": lambda args: {
                "delegate_to_agent": "macro_indicators"
            },
            "macro:calculate_indicators": lambda args: {
                "calculated": args.get("raw_data", {})
            },
            "analysis:run_fundamental_scan": self._handle_fundamental_scan,
            "analysis:submit_thesis": lambda args: args,
            "analysis:run_technical_scan": self._handle_technical_scan,
            "analysis:submit_technical_report": lambda args: args,
            "analysis:analyze_sentiment": lambda args: {
                "delegate_to_agent": "sentiment_analysis"
            },
            "analysis:submit_sentiment": lambda args: args,
            "analysis:analyze_macro": lambda args: {
                "delegate_to_agent": "macro_analysis"
            },
            "analysis:submit_macro_report": lambda args: args,
            "analysis:analyze_contrarian": lambda args: {
                "delegate_to_agent": "contrarian_analysis"
            },
            "analysis:submit_contrarian_report": lambda args: args,
            "retrieval:hybrid_search": lambda args: {"delegate_to_agent": "retrieval"},
            "retrieval:submit_retrieval_results": lambda args: args,
            "research:search_web": lambda args: {"delegate_to_agent": "web_search"},
            "research:submit_search_results": lambda args: args,
            "validation:validate_report": lambda args: {
                "report": args.get("report", ""),
                "user_query": args.get("user_query", ""),
                "is_valid": True,
            },
        }

        for name, handler in handlers.items():
            self.register_handler(name, handler)

        logger.info(f"Registered {len(handlers)} tool handlers")

    def _handle_fundamental_scan(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle fundamental scan tool."""
        raw_data_str = args.get("raw_data", "{}")
        if isinstance(raw_data_str, str):
            try:
                raw_data = json.loads(raw_data_str)
            except json.JSONDecodeError:
                raw_data = {}
        else:
            raw_data = raw_data_str

        scanner = FundamentalScanner()
        return scanner.scan(raw_data)

    def _handle_technical_scan(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle technical scan tool."""
        import pandas as pd
        from quant.indicators import TechnicalScanner

        ohlcv_data = args.get("ohlcv_data", [])
        if not ohlcv_data:
            return {"error": "No OHLCV data provided"}

        df = pd.DataFrame(ohlcv_data)
        scanner = TechnicalScanner()
        return scanner.scan(df)

    async def execute(self, tool_full_name: str, args: Dict[str, Any]) -> ToolResult:
        """
        Execute a tool by name with given arguments.

        Args:
            tool_full_name: Full tool name (namespace:name)
            args: Arguments to pass to the tool

        Returns:
            ToolResult with execution status and data
        """
        tool_def = self.registry.get_tool(tool_full_name)
        if not tool_def:
            return ToolResult(success=False, error=f"Tool not found: {tool_full_name}")

        handler = self._handlers.get(tool_full_name)
        if not handler:
            return ToolResult(
                success=False, error=f"No handler for tool: {tool_full_name}"
            )

        try:
            result = handler(args)

            if isinstance(result, dict):
                if "delegate_to_agent" in result:
                    return ToolResult(
                        success=True,
                        delegate_to_agent=result["delegate_to_agent"],
                    )
                return ToolResult(success=True, data=result)

            return ToolResult(success=True, data=result)

        except Exception as e:
            logger.error(
                f"Tool execution error for {tool_full_name}: {e}", exc_info=True
            )
            return ToolResult(success=False, error=str(e))

    def execute_sync(self, tool_full_name: str, args: Dict[str, Any]) -> ToolResult:
        """Synchronous wrapper for tool execution."""
        try:
            loop = None
            try:
                import asyncio

                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

            if loop:
                import asyncio

                return asyncio.run(self.execute(tool_full_name, args))
            else:
                return asyncio.run(self.execute(tool_full_name, args))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


tool_registry = ToolRegistry()
tool_executor = ToolExecutor(tool_registry)


def initialize_tool_system() -> None:
    """Initialize the tool system (registry and executor)."""
    tool_registry.initialize()
    tool_executor.initialize()
    logger.info("Tool system initialized")


initialize_tool_system()
