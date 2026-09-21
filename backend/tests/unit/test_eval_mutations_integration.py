from datetime import UTC, datetime

from app.core.agent_loop.publication import EvidenceFact, ReportDraft

from evals.mutations import publish_validator


def _fixture():
    evidence = {
        "price.latest": EvidenceFact(
            fact_id="price.latest",
            value=100,
            unit="INR",
            source_id="source:test",
            instrument="TCS.NS",
            observed_at=datetime(2026, 9, 20, tzinfo=UTC),
            quality_status="verified",
            source_url="https://example.test/source",
        )
    }
    draft = ReportDraft.model_validate(
        {
            "executive_summary": "Price is [[fact:price.latest]].",
            "key_drivers": ["Demand."],
            "detailed_analysis": "Price is [[fact:price.latest]].",
            "risks": ["Execution."],
            "final_view": "Review evidence.",
            "claims": [
                {
                    "claim_id": "claim-1",
                    "text": "Price is [[fact:price.latest]].",
                    "importance": "major",
                    "evidence_refs": ["citation-1"],
                    "numeric_refs": ["price.latest"],
                }
            ],
            "citations": [{"citation_id": "citation-1", "source_id": "source:test"}],
        }
    )
    return draft, evidence


def test_publish_validator_accepts_clean_and_rejects_unbound_number():
    draft, evidence = _fixture()
    assert publish_validator(draft, evidence).passed
    bad = draft.model_copy(update={"executive_summary": "Price is 999."})
    result = publish_validator(bad, evidence)
    assert not result.passed
    assert "numeric_claim_unbound" in result.reasons
