import pytest

from app.core.graph.nodes.autonomous_goal_node import autonomous_goal_node


@pytest.mark.asyncio
async def test_goal_node_output_satisfies_envelope_contract() -> None:
    from app.core.contracts.graph_node import validate_node_output_contract

    result = await autonomous_goal_node({"user_query": "AAPL setup"})
    assert validate_node_output_contract(result) == []


def test_contract_validator_reports_missing_required_fields() -> None:
    from app.core.contracts.graph_node import validate_node_output_contract

    errors = validate_node_output_contract({"status": "success"})
    assert any("missing required field" in error for error in errors)
