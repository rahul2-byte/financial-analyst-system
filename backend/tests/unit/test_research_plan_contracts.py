import pytest

from agents.financial.research.research_plan_node import research_plan_node


@pytest.mark.asyncio
async def test_research_plan_builds_agent_specific_questions_and_dependencies() -> None:
    result = await research_plan_node(
        {
            "user_query": "Assess INFY earnings risk",
            "goal": {"ticker": "INFY", "instruments": [{"trading_symbol": "INFY"}]},
            "approved_agents": ["fundamental_analysis", "contrarian_analysis"],
            "timeframe": "1y",
            "hypotheses": [
                {"statement": "Earnings quality may weaken"},
                {"statement": "Narrative risk may be underpriced"},
            ],
            "data_status": {
                "fundamentals": {"available": True, "coverage": 0.3, "freshness": 1.0},
                "news": {"available": True, "coverage": 1.0, "freshness": 1.0},
                "ohlcv": {"available": True, "coverage": 1.0, "freshness": 1.0},
                "macro": {"available": True, "coverage": 1.0, "freshness": 1.0},
            },
        }
    )

    tasks = {task["agent"]: task for task in result["tasks"]}
    assert result["next_action"] == "run_research_context"
    assert "INFY" in tasks["fundamental_analysis"]["research_question"]
    assert (
        tasks["fundamental_analysis"]["research_question"]
        != "Analyze fundamental analysis for INFY"
    )
    assert "profitability" in tasks["fundamental_analysis"]["missing_dimensions"]
    assert tasks["contrarian_analysis"]["depends_on"] == [
        "fundamental_analysis",
        "technical_analysis",
        "sentiment_analysis",
        "macro_analysis",
    ]


@pytest.mark.asyncio
async def test_research_plan_assigns_technical_dimensions_for_selected_technical_agent() -> (
    None
):
    result = await research_plan_node(
        {
            "user_query": "Analyse the HDFC stock",
            "goal": {
                "ticker": "HDFCBANK",
                "instruments": [{"trading_symbol": "HDFCBANK"}],
            },
            "approved_agents": ["technical_analysis"],
            "timeframe": "1y",
            "hypotheses": [
                {"statement": "Validate the stock through fundamental quality."},
                {"statement": "Look for narrative and macro invalidation."},
            ],
            "data_status": {
                "ohlcv": {"available": True, "coverage": 1.0, "freshness": 1.0},
            },
        }
    )

    technical = result["tasks"][0]
    assert technical["agent"] == "technical_analysis"
    assert technical["required_dimensions"] == [
        "price_action",
        "trend",
        "volatility",
    ]


@pytest.mark.asyncio
async def test_research_plan_contrarian_dependency_matches_required_macro_dimension() -> (
    None
):
    result = await research_plan_node(
        {
            "user_query": "Analyse the HDFC stock",
            "goal": {
                "ticker": "HDFCBANK",
                "instruments": [{"trading_symbol": "HDFCBANK"}],
            },
            "approved_agents": ["contrarian_analysis"],
            "timeframe": "1y",
            "hypotheses": [
                {"statement": "Validate fundamental quality and earnings durability."},
                {
                    "statement": "Identify whether market narrative, macro regime, or sector conditions could invalidate the thesis."
                },
            ],
            "data_status": {
                "fundamentals": {"available": True, "coverage": 1.0, "freshness": 1.0},
                "ohlcv": {"available": True, "coverage": 1.0, "freshness": 1.0},
                "news": {"available": True, "coverage": 1.0, "freshness": 1.0},
                "macro": {"available": True, "coverage": 1.0, "freshness": 1.0},
            },
        }
    )

    contrarian = result["tasks"][0]
    assert "macro_regime" in contrarian["required_dimensions"]
    assert "macro_analysis" in contrarian["depends_on"]


@pytest.mark.asyncio
async def test_research_plan_audit_logs_decisions() -> None:
    result = await research_plan_node(
        {
            "user_query": "Assess INFY earnings risk",
            "goal": {"ticker": "INFY", "instruments": [{"trading_symbol": "INFY"}]},
            "approved_agents": ["fundamental_analysis"],
            "timeframe": "1y",
            "hypotheses": [{"statement": "H1"}],
            "data_status": {
                "fundamentals": {"available": True, "coverage": 0.3, "freshness": 1.0}
            },
        }
    )

    audit = result["data"]["audit"]
    assert audit["node"] == "research_plan_node"
    assert audit["ticker"] == "INFY"

    summary = audit["decision_summary"]
    assert summary["assigned_agents"] == ["fundamental_analysis"]
    assert summary["task_count"] == 1
    assert "fundamental_analysis" in summary["dimensions_by_agent"]
