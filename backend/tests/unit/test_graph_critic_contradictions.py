import pytest

from app.core.graph.nodes.autonomous_quality_nodes import autonomous_critic_node


@pytest.mark.asyncio
async def test_critic_emits_directional_conflict_record_with_strong_evidence() -> None:
    state = {
        "results": {
            "synthesis": {
                "key_drivers": ["signal_mix=['bullish', 'bearish', 'neutral']"],
                "data_used": {
                    "ohlcv": {"freshness": 0.9},
                    "news": {"freshness": 0.9},
                },
            },
            "fundamental_analysis": {"analysis": "strong buy setup"},
            "sentiment_analysis": {"analysis": "strong sell pressure"},
            "macro_analysis": {"analysis": "neutral"},
        },
        "tool_registry": [
            {
                "tool_name": "analysis:run_fundamental_scan",
                "extracted_metrics": {"roe": 0.22, "fcf_margin": 0.16, "eps_growth": 0.18},
            },
            {
                "tool_name": "analysis:analyze_sentiment",
                "extracted_metrics": {"neg_news_ratio": 0.71, "sentiment_delta": -0.42, "volatility": 0.36},
            },
        ],
        "synthesis_confidence": 0.82,
        "evidence_strength": 0.78,
        "confidence_history": [0.71, 0.74],
        "confidence_components": {},
    }

    result = await autonomous_critic_node(state)

    assert result["critic_decision"] == "conflict"
    assert result["contradiction_records"]
    assert any(record["type"] == "directional" for record in result["contradiction_records"])


@pytest.mark.asyncio
async def test_critic_uses_evidence_gap_type_for_unsupported_conflict() -> None:
    state = {
        "results": {
            "synthesis": {
                "key_drivers": ["signal_mix=['bullish', 'bearish', 'neutral']"],
                "data_used": {"ohlcv": {"freshness": 0.95}},
            },
            "fundamental_analysis": {"analysis": "buy"},
            "sentiment_analysis": {"analysis": "sell"},
            "macro_analysis": {"analysis": "neutral"},
        },
        "tool_registry": [],
        "synthesis_confidence": 0.76,
        "evidence_strength": 0.6,
        "confidence_history": [0.7, 0.71],
        "confidence_components": {},
    }

    result = await autonomous_critic_node(state)

    assert result["critic_decision"] == "retry"
    assert any(record["type"] == "evidence_gap" for record in result["contradiction_records"])


@pytest.mark.asyncio
async def test_critic_emits_time_horizon_conflict_type() -> None:
    state = {
        "results": {
            "synthesis": {
                "key_drivers": ["signal_mix=['bullish', 'bearish', 'neutral']"],
                "data_used": {"ohlcv": {"freshness": 0.9}},
            },
            "fundamental_analysis": {"analysis": "long-term bullish accumulation"},
            "sentiment_analysis": {"analysis": "short-term bearish breakdown"},
            "macro_analysis": {"analysis": "neutral"},
        },
        "tool_registry": [
            {"tool_name": "analysis:run_fundamental_scan", "extracted_metrics": {"roe": 0.19, "margin": 0.14}},
            {"tool_name": "analysis:analyze_sentiment", "extracted_metrics": {"neg_news_ratio": 0.66, "momentum": -0.31}},
        ],
        "synthesis_confidence": 0.8,
        "evidence_strength": 0.72,
        "confidence_history": [0.69, 0.7],
        "confidence_components": {},
    }

    result = await autonomous_critic_node(state)

    assert any(record["type"] == "time_horizon" for record in result["contradiction_records"])
