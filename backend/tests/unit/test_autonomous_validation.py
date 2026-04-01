import pytest

from app.core.nodes.autonomous_validation_node import autonomous_validation_node


@pytest.mark.asyncio
async def test_validation_emits_strict_final_output_contract() -> None:
    result = await autonomous_validation_node(
        {
            "confidence_score": 0.8,
            "data_status": {},
            "results": {
                "synthesis": {
                    "decision": "watchlist",
                    "key_drivers": ["driver"],
                    "risks": ["risk"],
                    "data_used": {"ohlcv": {}},
                }
            },
        }
    )

    output = result["final_output"]
    required = {
        "decision",
        "confidence_score",
        "final_confidence",
        "key_drivers",
        "risks",
        "data_used",
        "insufficiency_markers",
        "reasoning",
        "next_action",
    }
    assert required.issubset(output.keys())
