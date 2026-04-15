"""Technical analysis graph node handler."""

import json
from typing import Any, Dict

from app.config import settings
from app.core.graph.graph_state import ResearchGraphState
from app.core.graph.node_helpers import build_node_error, build_node_success
from app.core.node_resources import NodeResources
from app.models.request_models import Message
from app.core.tools.tool_system import ToolNamespace, tool_executor, tool_registry
from app.config.constants import MODEL_REASONING


async def technical_analysis_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Uses LLM to fetch data via MCP and run TechnicalScanner."""
    current_step = state.get("current_step") or {}
    params = current_step.get("parameters", {})
    if not isinstance(params, dict):
        params = {}

    ticker = params.get("ticker", "UNKNOWN")

    tools = [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tool_registry.get_tools_by_namespace(ToolNamespace.RESEARCH)
        + tool_registry.get_tools_by_namespace(ToolNamespace.ANALYSIS)
        if t.name
        in ["postgres_query_database", "run_technical_scan", "submit_technical_report"]
    ]

    messages = [
        Message(
            role="system",
            content="You are a technical analyst. You must first query the 'ohlcv_data' table in the PostgreSQL database using 'postgres_query_database'. Then, pass the raw JSON data to 'run_technical_scan'. Finally, synthesize the results and submit using 'submit_technical_report'.",
        ),
        Message(role="user", content=f"Please analyze the technicals for {ticker}."),
    ]

    final_result = None
    response = None

    try:
        for _ in range(5):
            response = await resources.llm_service.generate_message(
                messages=messages, model=MODEL_REASONING, tools=tools
            )
            messages.append(response)

            if not response.tool_calls:
                break

            for tool_call in response.tool_calls:
                func = tool_call.get("function", {})
                short_name = func.get("name")
                args = json.loads(func.get("arguments", "{}"))

                if short_name.startswith("postgres_"):
                    full_name = f"mcp_postgres:{short_name.split('postgres_', 1)[1]}"
                else:
                    full_name = f"analysis:{short_name}"

                tool_result = await tool_executor.execute(full_name, args)

                result_content = json.dumps(
                    tool_result.error if not tool_result.success else tool_result.data,
                    ensure_ascii=True,
                    default=str,
                )

                if short_name == "submit_technical_report":
                    final_result = args
                    break

                messages.append(
                    Message(
                        role="tool",
                        content=result_content,
                        name=short_name,
                        tool_call_id=tool_call.get("id"),
                    )
                )

            if final_result:
                break

        if not final_result:
            final_content = response.content if response else "No analysis generated."
            final_result = {
                "trend": "Neutral",
                "report_summary": final_content,
                "key_indicators": {},
            }

        return build_node_success(
            agent_output_key="technical_analysis",
            agent_output=final_result,
            tool_name="analysis:submit_technical_report",
            input_parameters=params,
            tool_output=final_result,
        )
    except Exception as error:
        return build_node_error(error)
