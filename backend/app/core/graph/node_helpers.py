"""Shared helpers for graph node response shapes."""

from typing import Any

from app.core.contracts.tool_result import ToolResult


def build_node_success(
    *,
    agent_output_key: str,
    agent_output: Any,
    tool_name: str,
    input_parameters: dict[str, Any],
    tool_output: Any,
) -> dict[str, Any]:
    tool_result = ToolResult(
        tool_name=tool_name,
        input_parameters=input_parameters,
        output_data=tool_output,
    )
    tool_result.auto_extract_metrics()
    return {
        "agent_outputs": {agent_output_key: agent_output},
        "tool_registry": [tool_result.model_dump()],
    }


def build_node_error(error: Exception, prefix: str = "") -> dict[str, Any]:
    return {"errors": [f"{prefix}{str(error)}"]}
