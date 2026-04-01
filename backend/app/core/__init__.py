"""
Core module - LangGraph orchestration and agent infrastructure.

This module provides:
- Graph-based pipeline orchestration (LangGraph)
- Agent nodes for different research tasks
- State management for the research pipeline
- Error handling and retry logic
- Circuit breaker for external services
- Caching utilities

Usage:
    from app.core import PipelineOrchestrator, get_research_graph
    from app.core import get_logger, setup_logging
    from app.core import SessionLogger
"""

# Import error handling for missing dependencies
try:
    from app.config import settings

    _HAS_CONFIG = True
except ImportError:
    settings = None
    _HAS_CONFIG = False

# Logging
try:
    from app.core.logging import get_logger, setup_logging, SessionLogger

    _HAS_LOGGING = True
except ImportError:
    get_logger = setup_logging = SessionLogger = None
    _HAS_LOGGING = False

# Graph components (may require langgraph)
try:
    from app.core.graph.graph_builder import get_research_graph
    from app.core.graph.graph_state import ResearchGraphState, merge_dicts

    _HAS_GRAPH = True
except ImportError:
    get_research_graph = None
    ResearchGraphState = None
    merge_dicts = None
    _HAS_GRAPH = False

# Orchestration (may require langgraph)
try:
    from app.core.orchestrator import PipelineOrchestrator

    _HAS_ORCHESTRATOR = True
except ImportError:
    PipelineOrchestrator = None
    _HAS_ORCHESTRATOR = False

# Error handling
try:
    from app.core.error_handling import ErrorHandler

    _HAS_ERROR_HANDLER = True
except ImportError:
    ErrorHandler = None
    _HAS_ERROR_HANDLER = False

# Circuit breaker
try:
    from app.core.circuit_breaker import CircuitBreaker, get_circuit

    _HAS_CIRCUIT_BREAKER = True
except ImportError:
    CircuitBreaker = get_circuit = None
    _HAS_CIRCUIT_BREAKER = False

# Caching
try:
    from app.core.cache import Cache, cached_llm_response, cached_tool_result

    _HAS_CACHE = True
except ImportError:
    Cache = cached_llm_response = cached_tool_result = None
    _HAS_CACHE = False


__all__ = [
    # Config
    "settings",
    # Logging
    "get_logger",
    "setup_logging",
    "SessionLogger",
    # Graph
    "get_research_graph",
    "ResearchGraphState",
    "merge_dicts",
    # Orchestration
    "PipelineOrchestrator",
    # Error handling
    "ErrorHandler",
    # Circuit breaker
    "CircuitBreaker",
    "get_circuit",
    # Caching
    "Cache",
    "cached_llm_response",
    "cached_tool_result",
]
