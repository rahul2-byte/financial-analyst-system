import json
from typing import Dict, Any
from app.core.observability import observe, langfuse_context

from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.quality_control.schemas import AgentResponse, ValidationResult
from quant.validators import ReportValidator
from app.core.utils import clean_json_string
from agents.base import BaseAgent


class ValidationAgent(BaseAgent):
    """
    The final compliance checkpoint. Ensures that the final synthesized report
    does not guarantee returns, leak system data, or hallucinate off-topic.
    """

    SYSTEM_PROMPT = """
You are the Compliance and Validation Officer for a Financial Intelligence Platform.
Your job is to review the Draft Report against the User Query and the deterministic rule violations provided by the Python scanner.

CRITICAL RULES:
1. Do not add any new financial analysis.
2. If the Python scanner found 'violations', you MUST rewrite the offending parts of the report to be neutral and safe.
3. Ensure the report actually answers the User Query. If it doesn't, note it in the violations.
4. Your final output must EXACTLY match the ValidationResult JSON schema. Do not output anything outside of the JSON.
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
            }
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Executes the Python validator."""
        try:
            if tool_name == "run_deterministic_checks":
                draft_text = arguments.get("draft_text", "")
                results = self.validator.run_checks(draft_text)
                return json.dumps(results)
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:Validation:Execute")
    async def execute(
        self, user_query: str, step_number: int = 0, draft_report: str = ""
    ) -> AgentResponse:
        """
        Executes the validation loop.
        Forces the LLM to output the ValidationResult schema.
        """
        prompt = f"USER QUERY:\n{user_query}\n\nDRAFT REPORT:\n{draft_report}"

        messages = [
            Message(role="system", content=self.SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ]

        try:
            # Step 1: Tell the LLM to run the deterministic Python checks
            tid_checks = await self.emit_status(
                step_number, self.agent_name, "Running compliance checks...", status="running"
            )
            response_msg = await self.llm_service.generate_message(
                messages=messages, model=self.model, tools=self._get_tools()
            )
            await self.emit_status(
                step_number, self.agent_name, "Running compliance checks...", "Initial checks complete.", status="completed", tool_id=tid_checks
            )

            if not response_msg.content:
                response_msg.content = "Calling tool..."

            messages.append(response_msg)

            # Step 2: Execute python checker tool
            if response_msg.tool_calls:
                for tool_call in response_msg.tool_calls:
                    function_call = tool_call.get("function", {})
                    tool_name = function_call.get("name")
                    arguments_str = function_call.get("arguments", "{}")

                    if isinstance(arguments_str, str):
                        try:
                            arguments = json.loads(arguments_str)
                        except json.JSONDecodeError:
                            arguments = {}
                    else:
                        arguments = arguments_str

                    tid = await self.emit_status(
                        step_number, tool_name, "Scanning for regulatory violations...", status="running"
                    )
                    tool_result = self._execute_tool(tool_name, arguments)
                    await self.emit_status(
                        step_number,
                        tool_name,
                        "Scanning for regulatory violations...",
                        "Compliance scan complete.",
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

                # Step 3: LLM Synthesizes the final sanitized output
                if messages[-1].role == "tool":
                    tid_proc = await self.emit_status(
                        step_number, self.agent_name, "Processing scan results...", status="running"
                    )
                    intermediate_msg = await self.llm_service.generate_message(
                        messages=messages, model=self.model
                    )
                    if not intermediate_msg.content:
                        intermediate_msg.content = "Processed tool results."
                    await self.emit_status(
                        step_number, self.agent_name, "Processing scan results...", "Results processed.", status="completed", tool_id=tid_proc
                    )
                    messages.append(intermediate_msg)

                tid_final = await self.emit_status(
                    step_number, self.agent_name, "Finalizing report validation...", status="running"
                )
                schema_str = json.dumps(ValidationResult.model_json_schema())
                messages.append(
                    Message(
                        role="user",
                        content=(
                            f"Based on the scan results above, generate the final validation result as a JSON object matching this schema: {schema_str}\n\n"
                            "CRITICAL: You MUST return ONLY valid JSON. Do not wrap your response in markdown backticks (```json). "
                            "Do not include any conversational text or explanations."
                        ),
                    )
                )
                final_response_msg = await self.llm_service.generate_message(
                    messages=messages,
                    model=self.model,
                    response_format={"type": "json_object"},
                )
                await self.emit_status(
                    step_number, self.agent_name, "Finalizing report validation...", "Validation complete.", status="completed", tool_id=tid_final
                )
                final_content = final_response_msg.content
            else:
                # Fallback if it didn't call the tool
                tid_fallback = await self.emit_status(
                    step_number, self.agent_name, "Finalizing report validation...", status="running"
                )
                schema_str = json.dumps(ValidationResult.model_json_schema())
                messages.append(
                    Message(
                        role="user",
                        content=(
                            f"Generate the final validation result as a JSON object matching this schema: {schema_str}\n\n"
                            "CRITICAL: You MUST return ONLY valid JSON. Do not wrap your response in markdown backticks (```json). "
                            "Do not include any conversational text or explanations."
                        ),
                    )
                )
                final_response_msg = await self.llm_service.generate_message(
                    messages=messages,
                    model=self.model,
                    response_format={"type": "json_object"},
                )
                await self.emit_status(
                    step_number, self.agent_name, "Finalizing report validation...", "Validation complete.", status="completed", tool_id=tid_fallback
                )
                final_content = final_response_msg.content

            # Parse the strict JSON string
            try:
                if not final_content:
                    raise ValueError("Final content is empty")
                cleaned_content = clean_json_string(final_content)
                parsed_insights = json.loads(cleaned_content)
            except Exception:
                parsed_insights = {"raw_output": final_content}

            return AgentResponse(status="success", data=parsed_insights, errors=None)

        except Exception as e:
            return AgentResponse(status="failure", data={}, errors=[str(e)])
