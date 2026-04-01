import pytest

from app.core.graph.nodes.autonomous_quality_nodes import autonomous_synthesis_node
from app.core.graph.nodes.autonomous_research_nodes import autonomous_research_execution_node


@pytest.mark.asyncio
async def test_research_execution_collects_tool_registry_evidence(monkeypatch) -> None:
    async def _fake_agent(_state, _resources):
        return {
            "agent_outputs": {"fundamental_analysis": {"score": 0.9}},
            "tool_registry": [
                {
                    "tool_name": "analysis:run_fundamental_scan",
                    "input_parameters": {},
                    "output_data": {"score": 0.9, "pe_ratio": 12.0},
                    "extracted_metrics": {"score": 0.9, "pe_ratio": 12.0},
                }
            ],
        }

    monkeypatch.setitem(
        __import__("app.core.graph.nodes.autonomous_research_nodes", fromlist=["AGENT_NODE_MAP"]).AGENT_NODE_MAP,
        "fundamental_analysis",
        _fake_agent,
    )

    result = await autonomous_research_execution_node(
        {
            "tasks": [
                {
                    "task_id": "fundamental_analysis",
                    "agent": "fundamental_analysis",
                    "priority": "P0",
                    "parameters": {"ticker": "AAPL"},
                }
            ],
            "timeouts": {"task_timeout_s": 5.0, "stage_timeout_s": 10.0},
            "results": {},
        }
    )

    assert result["tool_registry"]
    assert result["tool_registry"][0]["extracted_metrics"]["pe_ratio"] == 12.0


@pytest.mark.asyncio
async def test_synthesis_evidence_strength_uses_real_tool_metrics() -> None:
    state = {
        "results": {
            "fundamental_analysis": {"analysis": "bullish setup"},
            "sentiment_analysis": {"analysis": "positive momentum"},
            "macro_analysis": {"analysis": "neutral backdrop"},
        },
        "tool_registry": [
            {
                "tool_name": "analysis:run_fundamental_scan",
                "extracted_metrics": {"roe": 0.21, "debt_to_equity": 0.33},
            },
            {
                "tool_name": "analysis:analyze_macro",
                "extracted_metrics": {"inflation": 0.03},
            },
        ],
        "data_status": {
            "ohlcv": {"available": True, "freshness": 0.9},
            "news": {"available": True, "freshness": 0.9},
            "fundamentals": {"available": True, "freshness": 0.9},
            "macro": {"available": True, "freshness": 0.9},
        },
    }

    result = await autonomous_synthesis_node(state)

    assert result["evidence_strength"] > 0.6
    assert any(
        isinstance(driver, str) and driver.startswith("metric:")
        for driver in result["results"]["synthesis"]["key_drivers"]
    )


@pytest.mark.asyncio
async def test_research_execution_preserves_agent_mapping_when_earlier_task_times_out(
    monkeypatch,
) -> None:
    import asyncio

    async def _slow_agent(_state, _resources):
        await asyncio.sleep(0.2)
        return {"agent_outputs": {"fundamental_analysis": {"analysis": "slow"}}}

    async def _fast_agent(_state, _resources):
        return {"agent_outputs": {"sentiment_analysis": {"analysis": "fast"}}}

    module = __import__("app.core.graph.nodes.autonomous_research_nodes", fromlist=["AGENT_NODE_MAP"])
    monkeypatch.setitem(module.AGENT_NODE_MAP, "fundamental_analysis", _slow_agent)
    monkeypatch.setitem(module.AGENT_NODE_MAP, "sentiment_analysis", _fast_agent)

    result = await autonomous_research_execution_node(
        {
            "tasks": [
                {
                    "task_id": "fundamental_analysis",
                    "agent": "fundamental_analysis",
                    "priority": "P0",
                    "parameters": {},
                },
                {
                    "task_id": "sentiment_analysis",
                    "agent": "sentiment_analysis",
                    "priority": "P1",
                    "parameters": {},
                },
            ],
            "timeouts": {"task_timeout_s": 0.05, "stage_timeout_s": 0.1},
            "results": {},
        }
    )

    assert "sentiment_analysis" in result["results"]
    assert result["results"]["sentiment_analysis"]["analysis"] == "fast"
    assert "fundamental_analysis" not in result["results"]
