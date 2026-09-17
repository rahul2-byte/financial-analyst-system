"""Deterministic terminal-state decision for an AgentLoop run."""

from __future__ import annotations


def terminal_status(
    *,
    failed_tools: int,
    successful_tools: int,
    requires_evidence: bool,
    successful_evidence_tools: int,
    invalid_evidence: bool,
    partial_provider_response: bool,
) -> str:
    if (
        (failed_tools > 0 and successful_tools == 0)
        or (requires_evidence and successful_evidence_tools == 0)
        or invalid_evidence
    ):
        return "insufficient_data"
    if failed_tools or partial_provider_response:
        return "partial"
    return "success"
