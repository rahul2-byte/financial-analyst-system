import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.core.node_resources import resources
from app.core.policies.json_parse_policy import parse_json_from_llm_response
from app.core.prompts import prompt_manager
from app.models.request_models import Message

logger = logging.getLogger(__name__)

NON_FINANCIAL_FALLBACK_RESPONSE = (
    "Hi! I focus on financial research and investment analysis. "
    "I can help with stock analysis, market trends, portfolio risk, and earnings breakdowns. "
    "Please ask a finance-related question to get started."
)


class IntentClassificationResult(BaseModel):
    label: Literal["financial", "non_financial", "ambiguous"]
    is_financial_request: bool
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    assistant_response: str = ""


def _build_fail_closed_result(message: str | None = None) -> IntentClassificationResult:
    return IntentClassificationResult(
        label="non_financial",
        is_financial_request=False,
        confidence=0.0,
        assistant_response=message or NON_FINANCIAL_FALLBACK_RESPONSE,
    )


async def classify_query_intent(
    user_query: str,
    conversation_history: list[dict[str, Any]] | None = None,
) -> IntentClassificationResult:
    history = conversation_history or []
    try:
        messages = [
            Message(
                role="system",
                content=prompt_manager.get_prompt(
                    "orchestrator.intent_classifier.system"
                ),
            )
        ]

        # Map conversation history to Message objects
        for msg in history[-8:]:
            messages.append(Message(role=msg["role"], content=msg["content"]))

        # Add current user query as its own message
        messages.append(
            Message(
                role="user",
                content=prompt_manager.get_prompt(
                    "orchestrator.intent_classifier.user",
                    user_query=user_query,
                ),
            )
        )

        response = await resources.llm_service.generate_message(
            messages=messages,
            model=settings.DEFAULT_LLM_MODEL,
            response_format={"type": "json_object"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Intent classifier request failed: %s", exc, exc_info=True)
        return _build_fail_closed_result()

    parsed = parse_json_from_llm_response(response.content)
    if not parsed:
        logger.warning(
            f"Intent classifier returned non-JSON content. Raw: {response.content}"
        )
        return _build_fail_closed_result()

    # Defensive: unwrap nested structures (e.g., [[...]] or [{...}])
    if isinstance(parsed, list):
        # Find the first dict element in the nested structure
        for item in parsed:
            if isinstance(item, dict):
                parsed = item
                break
            elif isinstance(item, list):
                # Flatten one level of nesting
                for inner in item:
                    if isinstance(inner, dict):
                        parsed = inner
                        break
                break

    if not isinstance(parsed, dict):
        logger.warning(
            f"Intent classifier returned non-dict after unwrapping: {type(parsed)}"
        )
        return _build_fail_closed_result()

    try:
        result = IntentClassificationResult.model_validate(parsed)
    except ValidationError:
        logger.warning(
            f"Intent classifier returned invalid schema: {parsed}", exc_info=True
        )
        return _build_fail_closed_result()

    if result.label == "financial":
        result.is_financial_request = True
        return result

    result.is_financial_request = False
    if not result.assistant_response.strip():
        result.assistant_response = NON_FINANCIAL_FALLBACK_RESPONSE
    return result
