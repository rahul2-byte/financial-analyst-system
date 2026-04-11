"""Fundamental analysis graph node handler."""

import json
from typing import Any, Dict

from app.config import settings
from app.core.graph.graph_state import ResearchGraphState
from app.core.graph.node_helpers import build_node_error, build_node_success
from app.core.node_resources import NodeResources
from app.models.request_models import Message
from app.core.tools.tool_system import ToolNamespace, tool_executor, tool_registry
from app.config.constants import MODEL_REASONING

async def fundamental_analysis_node(
    state: ResearchGraphState, resources: NodeResources
) -> Dict[str, Any]:
    """Uses LLM to fetch data via MCP and run FundamentalScanner."""
    current_step = state.get("current_step") or {}
    params = current_step.get("parameters", {})
    if not isinstance(params, dict):
        params = {}
        
    ticker = params.get("ticker", "UNKNOWN")
    
    # We provide the LLM with MCP tools (from RESEARCH namespace) and ANALYSIS tools
    tools = [
        {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
        for t in tool_registry.get_tools_by_namespace(ToolNamespace.RESEARCH) + tool_registry.get_tools_by_namespace(ToolNamespace.ANALYSIS)
        if t.name in ["postgres_query_database", "run_fundamental_scan", "submit_thesis"]
    ]
    
    messages = [
        Message(role="system", content="You are a fundamental financial analyst. Your goal is to analyze a company's valuation and health. You must first query the 'company_fundamentals' table in the PostgreSQL database using the 'postgres_query_database' tool. Then, pass the raw JSON data you retrieve into the 'run_fundamental_scan' tool. Finally, synthesize the results and submit your thesis using the 'submit_thesis' tool."),
        Message(role="user", content=f"Please analyze the fundamentals for {ticker}.")
    ]

    final_result = None
    tool_outputs = []
    response = None

    try:
        for _ in range(5): # Max 5 steps
            response = await resources.llm_service.generate_message(
                messages=messages, model=MODEL_REASONING, tools=tools
            )
            messages.append(response)

            if not response.tool_calls:
                # Agent stopped calling tools, use final response
                break

            for tool_call in response.tool_calls:
                func = tool_call.get("function", {})
                short_name = func.get("name")
                args = json.loads(func.get("arguments", "{}"))
                
                # Resolve full tool name (postgres MCP or ANALYSIS)
                if short_name.startswith("postgres_"):
                    full_name = f"mcp_postgres:{short_name.split('postgres_', 1)[1]}"
                else:
                    full_name = f"analysis:{short_name}"
                
                tool_result = await tool_executor.execute(full_name, args)

                result_content = json.dumps(
                    tool_result.error if not tool_result.success else tool_result.data, 
                    ensure_ascii=True, default=str
                )
                
                tool_outputs.append(tool_result)

                if short_name == "submit_thesis":
                    final_result = args
                    break
                
                messages.append(
                    Message(role="tool", content=result_content, name=short_name, tool_call_id=tool_call.get("id"))
                )
            
            if final_result:
                break
                
        if not final_result:
            final_content = response.content if response else "No analysis generated."
            final_result = {"investment_thesis": final_content, "key_findings": [], "confidence_score": 0.5}

        return build_node_success(
            agent_output_key="fundamental_analysis",
            agent_output=final_result,
            tool_name="analysis:submit_thesis",
            input_parameters=params,
            tool_output=final_result,
        )
    except Exception as error:
        return build_node_error(error)
