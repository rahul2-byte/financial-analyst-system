import json
import logging
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger(__name__)

# Handler Registry - maps tool names to handler functions
TOOL_HANDLERS: Dict[str, Callable] = {}


def register_handler(tool_name: str, handler: Callable) -> None:
    """Register a handler for a tool."""
    TOOL_HANDLERS[tool_name] = handler


# ==================== MARKET HANDLERS ====================

def handle_market_check_db_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle check_db_status tool."""
    from storage.sql.client import PostgresClient
    db = PostgresClient()
    status = db.is_db_up()
    return {"db_up": status}


def handle_market_get_table_names(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle get_table_names tool."""
    from storage.sql.client import PostgresClient
    db = PostgresClient()
    tables = db.get_table_names()
    return {"tables": tables}


def handle_market_get_column_names(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle get_column_names tool."""
    from storage.sql.client import PostgresClient
    db = PostgresClient()
    table_name = args.get("table_name", "")
    columns = db.get_column_names(table_name)
    return {"table": table_name, "columns": columns}


def handle_market_get_ticker_info(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle get_ticker_info tool."""
    from storage.sql.client import PostgresClient
    db = PostgresClient()
    ticker = args.get("ticker", "")
    info = db.get_ticker_info(ticker)
    return info


def handle_market_submit_offline_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle submit_offline_status tool."""
    return args


# ==================== DATA HANDLERS ====================

def handle_data_fetch_stock_data(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle fetch_stock_data tool - delegates to existing agent logic."""
    # This will be called from the node, which has access to the full agent
    # Return a marker that the agent should handle this
    return {"delegate_to_agent": "price_and_fundamentals"}


def handle_data_fetch_fundamentals(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle fetch_fundamentals tool - delegates to existing agent logic."""
    return {"delegate_to_agent": "price_and_fundamentals"}


def handle_data_submit_data_response(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle submit_data_response tool."""
    return args


# ==================== NEWS HANDLERS ====================

def handle_news_fetch_news(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle fetch_news tool - delegates to existing agent."""
    return {"delegate_to_agent": "market_news"}


def handle_news_search_vector_db(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle search_vector_db tool."""
    return {"delegate_to_agent": "retrieval"}


def handle_news_submit_news_summary(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle submit_news_summary tool."""
    return args


# ==================== MACRO HANDLERS ====================

def handle_macro_fetch_macro_data(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle fetch_macro_data tool - delegates to existing agent."""
    return {"delegate_to_agent": "macro_indicators"}


def handle_macro_calculate_indicators(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle calculate_indicators tool."""
    raw_data = args.get("raw_data", {})
    return {"calculated": raw_data}


# ==================== ANALYSIS HANDLERS ====================

def handle_analysis_run_fundamental_scan(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle run_fundamental_scan tool."""
    from quant.fundamentals import FundamentalScanner
    
    raw_data_str = args.get("raw_data", "{}")
    if isinstance(raw_data_str, str):
        try:
            raw_data = json.loads(raw_data_str)
        except json.JSONDecodeError:
            raw_data = {}
    else:
        raw_data = raw_data_str
    
    scanner = FundamentalScanner()
    results = scanner.scan(raw_data)
    return results


def handle_analysis_submit_thesis(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle submit_thesis tool."""
    return args


def handle_analysis_run_technical_scan(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle run_technical_scan tool."""
    from quant.indicators import TechnicalScanner
    import pandas as pd
    
    ohlcv_data = args.get("ohlcv_data", [])
    if not ohlcv_data:
        return {"error": "No OHLCV data provided"}
    
    df = pd.DataFrame(ohlcv_data)
    scanner = TechnicalScanner()
    results = scanner.scan(df)
    return results


def handle_analysis_submit_technical_report(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle submit_technical_report tool."""
    return args


def handle_analysis_analyze_sentiment(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle analyze_sentiment tool - delegates to LLM."""
    return {"delegate_to_agent": "sentiment_analysis"}


def handle_analysis_submit_sentiment(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle submit_sentiment tool."""
    return args


def handle_analysis_analyze_macro(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle analyze_macro tool - delegates to LLM."""
    return {"delegate_to_agent": "macro_analysis"}


def handle_analysis_submit_macro_report(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle submit_macro_report tool."""
    return args


def handle_analysis_analyze_contrarian(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle analyze_contrarian tool - delegates to LLM."""
    return {"delegate_to_agent": "contrarian_analysis"}


def handle_analysis_submit_contrarian_report(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle submit_contrarian_report tool."""
    return args


# ==================== RETRIEVAL HANDLERS ====================

def handle_retrieval_hybrid_search(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle hybrid_search tool - delegates to retrieval agent."""
    return {"delegate_to_agent": "retrieval"}


def handle_retrieval_submit_retrieval_results(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle submit_retrieval_results tool."""
    return args


# ==================== RESEARCH HANDLERS ====================

def handle_research_search_web(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle search_web tool - delegates to web search agent."""
    return {"delegate_to_agent": "web_search"}


def handle_research_submit_search_results(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle submit_search_results tool."""
    return args


# ==================== VALIDATION HANDLERS ====================

def handle_validation_validate_report(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle validate_report tool."""
    report = args.get("report", "")
    user_query = args.get("user_query", "")
    return {"report": report, "user_query": user_query, "is_valid": True}


# ==================== REGISTER ALL HANDLERS ====================

def _register_all_handlers() -> None:
    """Register all tool handlers."""
    handlers = [
        # Market
        ("market:check_db_status", handle_market_check_db_status),
        ("market:get_table_names", handle_market_get_table_names),
        ("market:get_column_names", handle_market_get_column_names),
        ("market:get_ticker_info", handle_market_get_ticker_info),
        ("market:submit_offline_status", handle_market_submit_offline_status),
        
        # Data
        ("data:fetch_stock_data", handle_data_fetch_stock_data),
        ("data:fetch_fundamentals", handle_data_fetch_fundamentals),
        ("data:submit_data_response", handle_data_submit_data_response),
        
        # News
        ("news:fetch_news", handle_news_fetch_news),
        ("news:search_vector_db", handle_news_search_vector_db),
        ("news:submit_news_summary", handle_news_submit_news_summary),
        
        # Macro
        ("macro:fetch_macro_data", handle_macro_fetch_macro_data),
        ("macro:calculate_indicators", handle_macro_calculate_indicators),
        
        # Analysis
        ("analysis:run_fundamental_scan", handle_analysis_run_fundamental_scan),
        ("analysis:submit_thesis", handle_analysis_submit_thesis),
        ("analysis:run_technical_scan", handle_analysis_run_technical_scan),
        ("analysis:submit_technical_report", handle_analysis_submit_technical_report),
        ("analysis:analyze_sentiment", handle_analysis_analyze_sentiment),
        ("analysis:submit_sentiment", handle_analysis_submit_sentiment),
        ("analysis:analyze_macro", handle_analysis_analyze_macro),
        ("analysis:submit_macro_report", handle_analysis_submit_macro_report),
        ("analysis:analyze_contrarian", handle_analysis_analyze_contrarian),
        ("analysis:submit_contrarian_report", handle_analysis_submit_contrarian_report),
        
        # Retrieval
        ("retrieval:hybrid_search", handle_retrieval_hybrid_search),
        ("retrieval:submit_retrieval_results", handle_retrieval_submit_retrieval_results),
        
        # Research
        ("research:search_web", handle_research_search_web),
        ("research:submit_search_results", handle_research_submit_search_results),
        
        # Validation
        ("validation:validate_report", handle_validation_validate_report),
    ]
    
    for tool_name, handler in handlers:
        register_handler(tool_name, handler)
    
    logger.info(f"Registered {len(handlers)} tool handlers")


# Initialize handlers
_register_all_handlers()


class ToolExecutorNode:
    """Node for centralized tool execution."""

    def __init__(self):
        from app.core.tool_registry import ToolRegistry

        self.registry = ToolRegistry()

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tools based on current state."""
        current_tool = state.get("current_tool")
        if not current_tool:
            return {"errors": ["No tool specified"]}

        tool_def = self.registry.get_tool(current_tool)
        if not tool_def:
            return {"errors": [f"Tool not found: {current_tool}"]}

        tool_args = state.get("tool_args", {})

        try:
            handler = TOOL_HANDLERS.get(current_tool)
            if handler:
                result = handler(tool_args)
                # Check if we need to delegate to an agent
                if isinstance(result, dict) and result.get("delegate_to_agent"):
                    return {"needs_agent": result["delegate_to_agent"], "tool_args": tool_args}
                return {
                    "tool_results": [result],
                    "last_tool_output": result,
                }
            return {"errors": [f"No handler for tool: {current_tool}"]}
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return {"errors": [str(e)]}


tool_executor = ToolExecutorNode()


async def execute_tool_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node function for tool execution."""
    return await tool_executor.execute(state)
