from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchGateResult:
    status: str
    code: str
    message: str
    retryable: bool


def evaluate_research_gate(
    *,
    required_agents: list[str],
    completed_agents: list[str],
    major_claim_count: int,
    verified_major_claim_count: int,
    evidence_strength: float,
    source_diversity: float,
    unresolved_conflicts: int,
) -> ResearchGateResult:
    missing_agents = [
        agent for agent in required_agents if agent not in completed_agents
    ]
    if missing_agents:
        return ResearchGateResult(
            "hard_stop",
            "REQUIRED_AGENT_MISSING",
            f"Missing required agents: {missing_agents}",
            False,
        )
    if major_claim_count > verified_major_claim_count:
        return ResearchGateResult(
            "hard_stop",
            "MAJOR_CLAIM_UNSUPPORTED",
            "Major claims must be verified before synthesis can pass.",
            False,
        )
    if unresolved_conflicts > 0:
        return ResearchGateResult(
            "hard_stop",
            "UNRESOLVED_CONFLICT",
            "Conflicting major claims remain unresolved.",
            False,
        )
    if source_diversity < 0.4:
        return ResearchGateResult(
            "retry", "SOURCE_DIVERSITY_LOW", "Source diversity below threshold.", True
        )
    if evidence_strength < 0.65:
        return ResearchGateResult(
            "retry", "EVIDENCE_STRENGTH_LOW", "Evidence strength below threshold.", True
        )
    return ResearchGateResult("pass", "OK", "Research quality gate passed.", False)
