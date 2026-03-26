import json
from typing import Dict, Any, List
from app.core.observability import observe, langfuse_context

from app.core.prompts import prompt_manager
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.quality_control.schemas import AgentResponse, ValidationResult
from quant.validators import ReportValidator
from agents.base import BaseAgent


class ValidationAgent(BaseAgent):
    """
    The final compliance checkpoint. Ensures that the final synthesized report
    does not guarantee returns, leak system data, or hallucinate off-topic.
    """

    def __init__(self, llm_service: LLMServiceInterface, model: str = "mistral-8b"):
        super().__init__(llm_service, model)
        self.validator = ReportValidator()

    def _get_tools(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_deterministic_checks",
                    "description": "Runs fast regex-based checks to find system leakages and financial guarantees.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "draft_text": {
                                "type": "string",
                                "description": "The raw draft report text.",
                            }
                        },
                        "required": ["draft_text"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_validation_result",
                    "description": "Submits the final compliance validation result.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "is_valid": {
                                "type": "boolean",
                                "description": "True if the report is safe to show to the user.",
                            },
                            "violations_found": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of rules the report broke.",
                            },
                            "final_approved_text": {
                                "type": "string",
                                "description": "The final sanitized and approved report text.",
                            },
                        },
                        "required": ["is_valid", "final_approved_text"],
                    },
                },
            },
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Executes the validation tools."""
        try:
            if tool_name == "run_deterministic_checks":
                draft_text = arguments.get("draft_text", "")
                results = self.validator.run_checks(draft_text)
                return json.dumps(results)
            elif tool_name == "submit_validation_result":
                return json.dumps(arguments)
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:Validation:Execute")
    async def execute(
        self, user_query: str, step_number: int = 0, draft_report: str = ""
    ) -> AgentResponse:
        """
        Executes the validation loop using a robust tool-based architecture.
        """
        messages: List[Message] = [
            Message(
                role="system", content=prompt_manager.get_prompt("validation.system")
            ),
            Message(
                role="user",
                content=prompt_manager.get_prompt(
                    "validation.user", user_query=user_query, draft_report=draft_report
                ),
            ),
        ]

        max_turns = 3
        current_turn = 0

        try:
            while current_turn < max_turns:
                response_msg = await self.llm_service.generate_message(
                    messages=messages, model=self.model, tools=self._get_tools()
                )

                if not response_msg.content:
                    response_msg.content = "Validating..."

                messages.append(response_msg)

                if response_msg.tool_calls:
                    for tool_call in response_msg.tool_calls:
                        function_call = tool_call.get("function", {})
                        tool_name = function_call.get("name")

                        arguments_str = function_call.get("arguments", "{}")
                        try:
                            arguments = (
                                json.loads(arguments_str)
                                if isinstance(arguments_str, str)
                                else arguments_str
                            )
                        except json.JSONDecodeError:
                            arguments = {}

                        # Final submission
                        if tool_name == "submit_validation_result":
                            final_data = self._execute_tool(tool_name, arguments)
                            return AgentResponse(
                                status="success",
                                data=json.loads(final_data),
                                errors=None,
                            )

                        # Execute deterministic checks
                        tid = await self.emit_status(
                            step_number,
                            tool_name,
                            "Scanning draft for compliance...",
                            status="running",
                        )
                        tool_result = self._execute_tool(tool_name, arguments)
                        await self.emit_status(
                            step_number,
                            tool_name,
                            "Scanning draft for compliance...",
                            "Scan complete.",
                            status="completed",
                            tool_id=tid,
                        )

                        langfuse_context.update_current_observation(
                            metadata={
                                "tool_name": tool_name,
                                "tool_args": arguments,
                                "tool_result": tool_result,
                            }
                        )

                        messages.append(
                            Message(
                                role="tool",
                                content=tool_result,
                                name=tool_name,
                                tool_call_id=tool_call.get("id"),
                            )
                        )
                    current_turn += 1
                else:
                    return AgentResponse(
                        status="success",
                        data={"response": response_msg.content},
                        errors=[
                            "Final output was text-only, not structured JSON via submit_validation_result tool."
                        ],
                    )

            return AgentResponse(
                status="failure",
                data={},
                errors=[
                    f"Agent failed to submit validation results within {max_turns} turns."
                ],
            )

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
