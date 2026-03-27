import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


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
            if tool_def.handler:
                result = await tool_def.handler(tool_args)
                return {
                    "tool_results": [result],
                    "last_tool_output": result,
                }
            return {"errors": ["Tool has no handler"]}
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return {"errors": [str(e)]}


tool_executor = ToolExecutorNode()


async def execute_tool_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node function for tool execution."""
    return await tool_executor.execute(state)
