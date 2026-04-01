import pytest
from app.core.graph.nodes.verification_node import detect_conflicts

def test_detect_conflicts_bullish_bearish():
    # 1. Fundamental Bullish, Technical Bearish
    agent_outputs = {
        "fundamental_analysis": "The company has strong growth, BULLISH outlook.",
        "technical_analysis": "RSI is overbought, SELL signal detected (Bearish)."
    }
    conflict = detect_conflicts(agent_outputs)
    assert conflict is not None
    assert "fundamental_analysis" in conflict.contending_agents
    assert "technical_analysis" in conflict.contending_agents

def test_detect_conflicts_consensus():
    # 2. Both Bullish
    agent_outputs = {
        "fundamental_analysis": "Strong buy recommendation.",
        "technical_analysis": "Upward trend, very bullish."
    }
    conflict = detect_conflicts(agent_outputs)
    assert conflict is None

def test_detect_conflicts_missing_data():
    # 3. Missing one agent
    agent_outputs = {
        "fundamental_analysis": "Bullish"
    }
    conflict = detect_conflicts(agent_outputs)
    assert conflict is None
