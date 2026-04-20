import pytest

from app.core.intent_classifier import classify_query_intent
from app.core.node_resources import resources


class _StubLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _StubLLMService:
    def __init__(self, content: str) -> None:
        self.content = content

    async def generate_message(self, messages, model, **kwargs):
        return _StubLLMResponse(self.content)


class _FailingLLMService:
    async def generate_message(self, messages, model, **kwargs):
        raise RuntimeError("llm down")


def _set_llm_service(value):
    previous = resources._llm_service
    setattr(resources, "_llm_service", value)
    return previous


@pytest.mark.asyncio
async def test_classify_query_intent_financial() -> None:
    previous = _set_llm_service(
        _StubLLMService(
            '{"label":"financial","is_financial_request":true,"confidence":0.91,"assistant_response":""}'
        )
    )
    try:
        result = await classify_query_intent("Analyze AAPL", [])
    finally:
        setattr(resources, "_llm_service", previous)

    assert result.label == "financial"
    assert result.is_financial_request is True


@pytest.mark.asyncio
async def test_classify_query_intent_non_financial() -> None:
    previous = _set_llm_service(
        _StubLLMService(
            '{"label":"non_financial","is_financial_request":false,"confidence":0.93,"assistant_response":"Please ask a finance question."}'
        )
    )
    try:
        result = await classify_query_intent("Write me a poem", [])
    finally:
        setattr(resources, "_llm_service", previous)

    assert result.is_financial_request is False
    assert "finance" in result.assistant_response.lower()


@pytest.mark.asyncio
async def test_classify_query_intent_fails_closed_on_invalid_json() -> None:
    previous = _set_llm_service(_StubLLMService("not-json"))
    try:
        result = await classify_query_intent("Analyze AAPL", [])
    finally:
        setattr(resources, "_llm_service", previous)

    assert result.label == "non_financial"
    assert result.is_financial_request is False


@pytest.mark.asyncio
async def test_classify_query_intent_fails_closed_on_exception() -> None:
    previous = _set_llm_service(_FailingLLMService())
    try:
        result = await classify_query_intent("Analyze AAPL", [])
    finally:
        setattr(resources, "_llm_service", previous)

    assert result.label == "non_financial"
    assert result.is_financial_request is False
