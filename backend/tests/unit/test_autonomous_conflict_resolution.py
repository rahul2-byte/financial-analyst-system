import pytest

from app.core.nodes.conflict_resolution_node import conflict_resolution_node


@pytest.mark.asyncio
async def test_conflict_resolution_returns_reconcile_payload() -> None:
    result = await conflict_resolution_node({"confidence_score": 0.6})

    assert result["status"] == "success"
    assert result["next_action"] == "run_synthesis"
    assert result["data"]["conflict_resolution"]["resolved"] is True
