import json
from typing import Dict, Any, Optional, List

from app.core.observability import observe, langfuse_context
from app.core.prompts import prompt_manager
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.orchestration.schemas import PlanData
from agents.base import BaseAgent
from agents.data_access.schemas import AgentResponse


class PlannerAgent(BaseAgent):
    """
    The orchestrator brain. It reads a complex user query and breaks it
    down into a deterministic JSON DAG of steps to be executed by sub-agents.
    """

    def __init__(self, llm_service: LLMServiceInterface, model: str = "mistral-8b"):
        super().__init__(llm_service, model)

    def _get_tools(self) -> list:
        # Dynamically generate tool parameters from the Pydantic schema
        schema = PlanData.model_json_schema()
        # Ensure the schema is compatible with tool-calling formats (Mistral/OpenAI)
        # It needs 'type', 'properties', and 'required'. 
        # Pydantic's schema includes these.
        return [
            {
                "type": "function",
                "function": {
                    "name": "submit_execution_plan",
                    "description": "Submits the final execution plan, classifying intent and routing the request to appropriate agents.",
                    "parameters": schema,
                },
            }
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Executes the requested tool."""
        try:
            if tool_name == "submit_execution_plan":
                # This tool is a data structure for the final answer.
                # We return the arguments themselves.
                return json.dumps(arguments)
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:Planner:Execute")
    async def execute(
        self,
        user_query: str,
        step_number: int = 0,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentResponse:
        """
        Takes a user query and returns a structured Execution Plan wrapped in AgentResponse.
        """
        if context is None:
            context = {}

        conversation_history = context.get("conversation_history", [])

        # Construct the context-aware prompt data
        prompt_data = {
            "user_query": user_query,
            "system_context": context,
            "conversation_history": conversation_history,
        }

        messages: List[Message] = [
            Message(role="system", content=prompt_manager.get_prompt("planner.system")),
            Message(
                role="user",
                content=prompt_manager.get_prompt(
                    "planner.user", user_json=json.dumps(prompt_data)
                ),
            ),
        ]

        max_turns = 2
        last_error = None

        try:
            for i in range(max_turns):
                if i > 0 and last_error:
                    messages.append(Message(role="user", content=prompt_manager.get_prompt("planner.feedback", error=str(last_error))))

                tid = await self.emit_status(
                    step_number,
                    self.agent_name,
                    "Brainstorming research strategy...",
                    status="running",
                )
                
                response_msg = await self.llm_service.generate_message(
                    messages=messages, model=self.model, tools=self._get_tools()
                )
                messages.append(response_msg)

                if not response_msg.tool_calls:
                    # If the LLM returns text without calling the submission tool, 
                    # we return it but flag it may not be correctly structured for the orchestrator.
                    await self.emit_status(
                        step_number,
                        self.agent_name,
                        "Brainstorming research strategy...",
                        "Plan generated (text only).",
                        status="completed",
                        tool_id=tid,
                    )
                    return AgentResponse(
                        status="success",
                        data={"assistant_response": response_msg.content},
                        errors=["Final output was text-only, not structured JSON via submit_execution_plan tool."]
                    )

                # Find the 'submit_execution_plan' call
                for tool_call in response_msg.tool_calls:
                    function_call = tool_call.get("function", {})
                    tool_name = function_call.get("name")
                    
                    if tool_name == "submit_execution_plan":
                        arguments_str = function_call.get("arguments", "{}")
                        try:
                            arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
                            
                            # Validate against PlanData before returning
                            plan_data = PlanData.model_validate(arguments)
                            
                            await self.emit_status(
                                step_number,
                                self.agent_name,
                                "Brainstorming research strategy...",
                                "Plan generated successfully.",
                                status="completed",
                                tool_id=tid,
                            )
                            
                            return AgentResponse(
                                status="success", data=plan_data.model_dump(), errors=None
                            )
                        except Exception as parse_error:
                            last_error = parse_error
                            # Log and retry if possible
                            langfuse_context.update_current_observation(metadata={"parse_error": str(parse_error)})
                            continue # Try next tool call or loop again

            # If the loop finishes without a valid submission.
            return AgentResponse(
                status="failure",
                data={},
                errors=[f"Agent failed to submit a valid execution plan within {max_turns} turns. Last error: {str(last_error)}"]
            )

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
