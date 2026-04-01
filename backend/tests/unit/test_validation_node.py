import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.graph.nodes.validation_node import validation_node
from app.core.graph.nodes.verification_node import verification_node


@pytest.mark.asyncio
@patch("app.core.graph.nodes.validation_node.ReportValidator")
async def test_validation_node_makes_single_llm_call(mock_validator_cls):
    mock_validator = mock_validator_cls.return_value
    mock_validator.run_checks.return_value = {
        "is_critical_failure": False,
        "has_violations": False,
        "processed_text": "processed report",
    }

    llm_response = SimpleNamespace(
        tool_calls=[
            {
                "function": {
                    "name": "submit_validation_result",
                    "arguments": '{"is_compliant": true, "violations": [], "warnings": [], "confidence": 0.9}',
                }
            }
        ]
    )

    resources = SimpleNamespace(
        llm_service=SimpleNamespace(generate_message=AsyncMock(return_value=llm_response))
    )

    state = {
        "user_query": "Analyze AAPL",
        "draft_report": "Draft report",
    }

    result = await validation_node(state, resources)

    assert result["final_report"] == "processed report"
    assert resources.llm_service.generate_message.call_count == 1


@pytest.mark.asyncio
async def test_verification_mismatch_does_not_emit_terminal_errors():
    state = {
        "draft_report": "Revenue is 99999",
        "tool_registry": [
            {
                "tool_name": "analysis:test",
                "input_parameters": {},
                "output_data": {"revenue": 100.0},
                "extracted_metrics": {"revenue": 100.0},
            }
        ],
        "verification_retry_count": 0,
    }

    result = await verification_node(state, resources=SimpleNamespace())

    assert result["verification_passed"] is False
    assert "verification_feedback" in result
    assert "errors" not in result
