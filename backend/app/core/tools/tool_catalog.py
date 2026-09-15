"""Tool definitions and registry for the AgentLoop runtime."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

class ToolNamespace(str, Enum):
    """Enumeration of tool namespaces."""

    MARKET = "market"
    DATA = "data"
    NEWS = "news"
    MACRO = "macro"
    ANALYSIS = "analysis"
    RESEARCH = "research"
    VALIDATION = "validation"
    INTERACTION = "interaction"


@dataclass
class ToolDefinition:
    """Definition of a tool with metadata and handler."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any] | None = None
    namespace: ToolNamespace = ToolNamespace.DATA

    @property
    def full_name(self) -> str:
        return f"{self.namespace.value}:{self.name}"


@dataclass
class ToolResult:
    """Result of tool execution."""

    success: bool
    data: Any = None
    error: str | None = None
    delegate_to_agent: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"success": self.success}
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
        self._tools: dict[str, ToolDefinition] = {}
        self._initialized = False

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool in the registry."""
        self._tools[tool.full_name] = tool
        logger.debug(f"Registered tool: {tool.full_name}")

    def get_tool(self, full_name: str) -> ToolDefinition | None:
        """Get a tool by its full name (namespace:name)."""
        return self._tools.get(full_name)

    def list_tools(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_tools_by_namespace(
        self, namespace: str | ToolNamespace
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
                name="submit_offline_status",
                description="Submits the final offline data availability status.",
                parameters={
                    "type": "object",
                    "properties": {
                        "data_available": {"type": "boolean"},
                        "ticker_used": {"type": "string"},
                        "reasoning": {"type": "string"},
                        "ohlcv_data": {
                            "type": "object",
                            "description": "Normalized OHLCV data returned by the market-data provider",
                        },
                        "fundamentals_data": {
                            "type": "object",
                            "description": "The exact JSON object returned by get_fundamentals_info",
                        },
                        "news_data": {
                            "type": "object",
                            "description": "The exact JSON object returned by get_news_info",
                        },
                        "macro_data": {
                            "type": "object",
                            "description": "The exact JSON object returned by get_macro_info",
                        },
                    },
                    "required": [
                        "data_available",
                        "ticker_used",
                        "reasoning",
                        "ohlcv_data",
                        "fundamentals_data",
                        "news_data",
                        "macro_data",
                    ],
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
                description="Fetches news articles and headlines for a ticker.",
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "days": {"type": "integer"},
                    },
                    "required": ["ticker"],
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
                description="Fetches verified fundamentals for a ticker and runs deterministic valuation, health, and profitability analysis. Use Yahoo Finance symbols; for NSE use .NS (HDFC Bank is HDFCBANK.NS, not HDB).",
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Yahoo Finance ticker symbol",
                        }
                    },
                    "required": ["ticker"],
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
                name="run_technical_scan",
                description="Fetches verified OHLCV for a ticker and calculates RSI, MACD, and Bollinger Bands deterministically. Use Yahoo Finance symbols; for NSE use .NS (HDFC Bank is HDFCBANK.NS, not HDB).",
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Yahoo Finance ticker symbol",
                        },
                    },
                    "required": ["ticker"],
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
            ToolDefinition(
                name="ask_user",
                description="Ask the user one concise clarification question before continuing research.",
                parameters={
                    "type": "object",
                    "properties": {"question": {"type": "string"}},
                    "required": ["question"],
                },
                namespace=ToolNamespace.INTERACTION,
            ),
        ]

        for tool in tools:
            self.register(tool)

        logger.info(f"Registered {len(self._tools)} predefined tools")
