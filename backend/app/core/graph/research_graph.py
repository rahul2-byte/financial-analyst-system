import logging
import json
import asyncio
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from app.core.graph.agent_map import AGENT_NODE_MAP
from app.core.prompts import prompt_manager
from app.core.node_resources import NodeResources
from app.config import settings
from app.models.request_models import Message

logger = logging.getLogger(__name__)

async def research_planner_node(state: Dict[str, Any], resources: NodeResources) -> Dict[str, Any]:

    """Dynamically selects research lenses."""
    user_query = state.get("user_query", "")
    manifest = state.get("data_manifest", {})
    conflict_record = state.get("conflict_record")
    llm_service = resources.llm_service
    
    conflict_context = ""
    if conflict_record:
        conflict_context = f"\n\nCRITICAL: A sentiment conflict was detected: {json.dumps(conflict_record)}. Re-evaluate focusing on consensus or clearly justified divergence."

    prompt = prompt_manager.get_prompt(
        "orchestrator.research_planner",
        user_query=user_query,
        manifest=json.dumps(manifest),
        conflict_context=conflict_context,
        selected_agents=list(AGENT_NODE_MAP.keys())
    )
    
    model = settings.DEFAULT_LLM_MODEL
    resp = await llm_service.generate_message(
        messages=[Message(role="user", content=prompt)],
        model=model
    )
    # Simple parsing for demo
    from app.core.policies.json_parse_policy import parse_json_from_llm_response
    parsed = parse_json_from_llm_response(resp.content)
    
    selected = ["fundamental_analysis", "technical_analysis"]
    if parsed and "selected_agents" in parsed:
        selected = parsed["selected_agents"]
    
    return {"selected_agents": selected}

async def research_execution_node(state: Dict[str, Any], resources: NodeResources) -> Dict[str, Any]:
    """Executes selected agents in parallel."""
    selected = state.get("selected_agents", [])
    manifest = state.get("data_manifest", {})
    ticker = manifest.get("ticker")
    
    tasks = []
    for agent in selected:
        node_func = AGENT_NODE_MAP.get(agent)
        if node_func:
            # Prepare dummy step parameters
            step = {"parameters": {"ticker": ticker, "query": state.get("user_query")}}
            modified_state = {**state, "current_step": step}
            tasks.append(node_func(modified_state, resources))
            
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    agent_outputs = {}
    errors = []
    for agent, res in zip(selected, results):
        if isinstance(res, Exception):
            logger.error(f"Agent {agent} failed: {res}")
            errors.append(f"Agent {agent} failed: {str(res)}")
        elif isinstance(res, dict):
            if "errors" in res and res["errors"]:
                logger.error(f"Agent {agent} returned errors: {res['errors']}")
                errors.extend(res["errors"])
            
            if "agent_outputs" in res:
                # Merge outputs
                agent_outputs.update(res["agent_outputs"])
            
    return {
        "agent_outputs": agent_outputs,
        "errors": errors,
        "failed_node": "research_subgraph" if errors else None
    }

from app.core.graph.graph_state import ResearchGraphState

from functools import partial
from app.core.node_resources import resources

def build_research_graph():
    graph = StateGraph(ResearchGraphState)
    
    graph.add_node("planner", partial(research_planner_node, resources=resources))
    graph.add_node("execution", partial(research_execution_node, resources=resources))
    
    graph.set_entry_point("planner")
    graph.add_edge("planner", "execution")
    graph.add_edge("execution", END)
    
    return graph.compile()
