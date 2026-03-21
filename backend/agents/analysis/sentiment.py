import json
from typing import Dict, Any, Optional
from app.core.observability import observe, langfuse_context

from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from agents.analysis.schemas import AgentResponse, QualitativeInsights
from quant.nlp_scorer import NLPScorer
from app.core.utils import clean_json_string


class SentimentAnalysisAgent:
    """
    Hybrid Agent combining deterministic FinBERT scoring (via Python)
    with LLM-based reasoning to extract actionable insights from unstructured text.
    """

    SYSTEM_PROMPT = """
You are the Qualitative Sentiment Analyst for a Financial Intelligence Platform.
Your job is to synthesize raw text (news, transcripts) alongside mathematical FinBERT sentiment scores provided to you.

CRITICAL RULES:
1. You DO NOT perform any math or generate your own probability scores. Use the FinBERT scores provided by your tool.
2. Read the text to extract specific details: order book updates, challenges, and entity impacts (competitors, suppliers).
3. CONTRADICTION DETECTION: You must compare the FinBERT score against your human-like reading of the text. If the score is 'Bullish' but the text describes a massive lawsuit or debt default, you MUST flag `is_contradictory` as True and explain why.
4. Your final output must EXACTLY match the QualitativeInsights JSON schema. Do not output anything outside of the JSON.
    """

    def __init__(self, llm_service: LLMServiceInterface, model: str = "mistral-8b"):
        self.llm = llm_service
        self.model = model
        self.scorer = NLPScorer()

    def _get_tools(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_finbert_analysis",
                    "description": "Runs deterministic FinBERT sentiment scoring and forward-looking tense parsing on raw text.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "The raw unstructured text to analyze.",
                            }
                        },
                        "required": ["text"],
                    },
                },
            }
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Executes the NLP scorer tool."""
        try:
            if tool_name == "run_finbert_analysis":
                text = arguments.get("text", "")
                if not text:
                    return json.dumps({"error": "No text provided"})

                # Run the deterministic python layer
                results = self.scorer.analyze_text(text)
                return json.dumps(results)
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @observe(name="Agent:Sentiment:Execute")
    async def execute(
        self, user_query: str, raw_text_data: Optional[str] = None
    ) -> AgentResponse:
        """
        Executes the agent loop.
        Forces the LLM to return the exact QualitativeInsights Pydantic model structure.
        """
        prompt = user_query
        if raw_text_data:
            # We truncate massive transcripts slightly so the prompt doesn't explode,
            # though the ideal architecture uses RAG before this point.
            truncated_text = raw_text_data[:15000]
            prompt += f"\n\nHere is the raw text you must analyze:\n{truncated_text}"

        messages = [
            Message(role="system", content=self.SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ]

        try:
            # Step 1: The LLM should decide to call the FinBERT tool to get the mathematical scores
            response_msg = await self.llm.generate_message(
                messages=messages, model=self.model, tools=self._get_tools()
            )

            messages.append(response_msg)

            # Step 2: Execute FinBERT tool if requested
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

                    tool_result = self._execute_tool(tool_name, arguments)

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

                # Step 3: LLM Synthesizes the final output in the strict QualitativeInsights schema
                # We add the schema to the prompt for the final turn and ensure role alternation
                messages.append(
                    Message(
                        role="user",
                        content=f"Based on the analysis results above, synthesize the final qualitative analysis into a JSON object matching this schema: {json.dumps(QualitativeInsights.model_json_schema())}",
                    )
                )
                final_response_msg = await self.llm.generate_message(
                    messages=messages,
                    model=self.model,
                    response_format={"type": "json_object"},
                )
                final_content = final_response_msg.content
            else:
                # Fallback if it didn't call the tool (rare but possible)
                messages.append(
                    Message(
                        role="user",
                        content=f"Please synthesize your findings into a JSON object matching this schema: {json.dumps(QualitativeInsights.model_json_schema())}",
                    )
                )
                final_response_msg = await self.llm.generate_message(
                    messages=messages,
                    model=self.model,
                    response_format={"type": "json_object"},
                )
                final_content = final_response_msg.content

            # Parse the strict JSON string back into a dict for our standard AgentResponse
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
