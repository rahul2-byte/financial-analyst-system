"""Stateless planner node - generates execution plan from user query."""
import json
import logging
from typing import Dict, Any

from app.core.agent_factories import LLMServiceFactory
from app.core.prompts import prompt_manager
from app.models.request_models import Message
from agents.orchestration.schemas import PlanData

logger = logging.getLogger(__name__)


async def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stateless node that generates execution plan from user query.
    
    Replaces class-based PlannerAgent with pure function.
    """
    llm_service = LLMServiceFactory.get_llm_service()
    model = "mistral-8b"  # Could be moved to config
    
    user_query = state.get("user_query", "")
    conversation_history = state.get("conversation_history", [])
    
    logger.info(f"Planner node processing query: {user_query}")
    
    try:
        prompt_data = {
            "user_query": user_query,
            "system_context": {},
            "conversation_history": conversation_history,
        }
        
        messages = [
            Message(role="system", content=prompt_manager.get_prompt("planner.system")),
            Message(
                role="user",
                content=prompt_manager.get_prompt(
                    "planner.user", user_json=json.dumps(prompt_data)
                ),
            ),
        ]
        
        tools = [{
            "type": "function",
            "function": {
                "name": "submit_execution_plan",
                "description": "Submits the final execution plan",
                "parameters": PlanData.model_json_schema(),
            }
        }]
        
        response = await llm_service.generate_message(
            messages=messages, model=model, tools=tools
        )
        
        if response.tool_calls:
            for tool_call in response.tool_calls:
                func = tool_call.get("function", {})
                if func.get("name") == "submit_execution_plan":
                    args_str = func.get("arguments", "{}")
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    
                    plan_data = PlanData.model_validate(args)
                    
                    logger.info(f"Planner generated {len(plan_data.execution_steps)} steps")
                    
                    return {
                        "plan": plan_data.model_dump(),
                        "errors": [],
                    }
        
        return {
            "plan": None,
            "errors": ["Planner failed to generate valid execution plan"],
        }
        
    except Exception as e:
        logger.error(f"Planner node error: {e}", exc_info=True)
        return {
            "plan": None,
            "errors": [f"Planning failed: {str(e)}"],
        }
