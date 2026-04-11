import pytest

from agents.quality.evaluator_node import evaluator_node
from app.core.node_resources import resources


class _StubLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content
        self.tool_calls = None


class _StaticLLMService:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    async def generate_message(self, messages, model, tools=None):
        self.calls += 1
        return _StubLLMResponse(self.content)


def _set_llm_service(stub):
    previous = resources._llm_service
    setattr(resources, "_llm_service", stub)
    return previous


@pytest.mark.asyncio
async def test_evaluator_node_parses_llm_json_result() -> None:
    stub = _StaticLLMService(
        '{"score": 0.82, "error_type": "none", "feedback": "Grounded and complete."}'
    )
    previous = _set_llm_service(stub)
    try:
        result = await evaluator_node(
            {
                "user_query": "Analyze HDFCBANK",
                "final_output": {
                    "decision": "watchlist",
                    "reasoning": "Grounded response",
                    "key_drivers": [],
                    "risks": [],
                    "data_used": {},
                    "insufficiency_markers": [],
                    "next_action": "complete",
                    "confidence_score": 0.82,
                    "final_confidence": 0.82,
                },
            }
        )
    finally:
        setattr(resources, "_llm_service", previous)

    assert stub.calls == 1
    assert result["evaluation_result"]["score"] == 0.82
    assert result["evaluation_passed"] is True
    assert result["next_action"] == "run_router"


@pytest.mark.asyncio
async def test_evaluator_node_falls_back_for_invalid_llm_output() -> None:
    stub = _StaticLLMService("not json")
    previous = _set_llm_service(stub)
    try:
        result = await evaluator_node(
            {
                "user_query": "Analyze HDFCBANK",
                "final_output": {
                    "decision": "watchlist",
                    "reasoning": "Incomplete",
                    "key_drivers": [],
                    "risks": [],
                    "data_used": {},
                    "insufficiency_markers": ["news"],
                    "next_action": "complete",
                    "confidence_score": 0.5,
                    "final_confidence": 0.5,
                },
            }
        )
    finally:
        setattr(resources, "_llm_service", previous)

    assert result["evaluation_result"]["error_type"] == "incomplete_response"
    assert result["evaluation_passed"] is False
    assert result["next_action"] == "run_router"
    assert result["force_replan"] is True


@pytest.mark.asyncio
async def test_evaluator_node_fails_closed_when_llm_output_is_invalid() -> None:
    stub = _StaticLLMService("not json")
    previous = _set_llm_service(stub)
    try:
        result = await evaluator_node(
            {
                "user_query": "Analyze HDFCBANK",
                "validation_passed": True,
                "final_output": {
                    "decision": "watchlist",
                    "reasoning": "Looks valid",
                    "key_drivers": [],
                    "risks": [],
                    "data_used": {},
                    "insufficiency_markers": [],
                    "next_action": "complete",
                    "confidence_score": 0.92,
                    "final_confidence": 0.92,
                },
            }
        )
    finally:
        setattr(resources, "_llm_service", previous)

    assert result["evaluation_passed"] is False
    assert result["evaluation_result"]["error_type"] == "reasoning_error"
    assert result["evaluation_result"]["score"] < 0.8
    assert result["next_action"] == "run_router"
