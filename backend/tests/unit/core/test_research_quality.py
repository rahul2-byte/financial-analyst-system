from app.core.research_quality import evaluate_research_gate


def test_research_gate_blocks_major_claim_without_support():
    gate = evaluate_research_gate(
        required_agents=["fundamental_analysis"],
        completed_agents=["fundamental_analysis"],
        major_claim_count=1,
        verified_major_claim_count=0,
        evidence_strength=0.9,
        source_diversity=0.9,
        unresolved_conflicts=0,
    )

    assert gate.status == "hard_stop"
    assert gate.code == "MAJOR_CLAIM_UNSUPPORTED"


def test_research_gate_retries_when_source_diversity_is_too_low():
    gate = evaluate_research_gate(
        required_agents=["fundamental_analysis", "sentiment_analysis"],
        completed_agents=["fundamental_analysis", "sentiment_analysis"],
        major_claim_count=1,
        verified_major_claim_count=1,
        evidence_strength=0.75,
        source_diversity=0.2,
        unresolved_conflicts=0,
    )

    assert gate.status == "retry"
    assert gate.retryable is True
