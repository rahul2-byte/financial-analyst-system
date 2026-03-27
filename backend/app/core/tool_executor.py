import logging
from typing import Dict, Any, Optional

from app.core.tool_registry import ToolRegistry
from app.core.graph_state import ResearchGraphState

logger = logging.getLogger(__name__)


class ToolExecutorNode:
    """Centralized node for executing tool handlers from the ToolRegistry."""

    def __init__(self, registry: Optional[ToolRegistry] = None):
        self.registry = registry if registry is not None else ToolRegistry()

    async def execute(self, state: ResearchGraphState) -> Dict[str, Any]:
        """
        Execute the tool specified in state.

        Args:
            state: The current graph state containing current_tool and tool_args

        Returns:
            Updated state dict with tool_result or errors
        """
        current_tool = state.get("current_tool")
        tool_args = state.get("tool_args", {})

        if not current_tool:
            logger.error("No current_tool in state")
            return {
                "errors": ["current_tool is required but not found in state"],
            }

        tool_def = self.registry.get_tool(current_tool)
        if not tool_def:
            logger.error(f"Tool not found: {current_tool}")
            return {
                "errors": [f"Tool not found: {current_tool}"],
            }

        if not tool_def.handler:
            logger.error(f"No handler registered for tool: {current_tool}")
            return {
                "errors": [f"No handler registered for tool: {current_tool}"],
            }

        try:
            handler = tool_def.handler
            if callable(handler):
                result = await handler(**tool_args)
                logger.info(f"Tool {current_tool} executed successfully")
                return {
                    "tool_result": result,
                }
            else:
                logger.error(f"Handler for {current_tool} is not callable")
                return {
                    "errors": [f"Handler for {current_tool} is not callable"],
                }
        except Exception as e:
            logger.error(f"Error executing tool {current_tool}: {e}", exc_info=True)
            return {
                "errors": [f"Handler execution error: {str(e)}"],
            }


async def execute_tool_node(state: ResearchGraphState) -> Dict[str, Any]:
    """
    LangGraph node function for executing tools.

    This is the main entry point used in LangGraph workflows.

    Args:
        state: The current research graph state

    Returns:
        Dict with updated state containing tool_result or errors
    """
    node = ToolExecutorNode()
    return await node.execute(state)
